"""
EvalObserver - real-time interview evaluation observer.

After each turn, a background task can:
1. Ask a secondary LLM for a concise turn-level assessment
2. Update the in-memory draft
3. Sync the draft to the data service

The main interview flow should never block on these tasks, but shutdown must be
predictable: once an interview is ending, no late draft writes should appear.
"""

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait as wait_futures
from typing import Dict, List, Optional, Set


def _coerce_score(value) -> int:
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(1, min(score, 10))


def _pass_level_from_score(score: int) -> str:
    if score >= 9:
        return "excellent"
    if score >= 7:
        return "pass"
    if score >= 5:
        return "weak_pass"
    if score > 0:
        return "fail"
    return ""


DEFAULT_DIMENSION = {
    "name": "综合表现",
    "rubric": "结合本轮问题，评估候选人的表达、逻辑、经验真实性和岗位匹配度。",
    "pass_criteria": "回答能够正面回应问题，并给出清晰事实、过程或例子。",
}


class EvalObserver:
    def __init__(self, session_id: str, llm_client, data_client=None):
        self.session_id = session_id
        self.llm_client = llm_client
        self.data_client = data_client
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._accepting = True
        self._shutdown = False
        self._push_callback = None
        self._futures: Set = set()
        self._pending_turns: Set[str] = set()
        self._completed_turn_ids: Set[str] = set()
        self.draft: Dict = {
            "strengths": [],
            "weaknesses": [],
            "turn_notes": [],
            "last_turn": 0,
        }

    def set_push_callback(self, callback):
        """Register the SSE push callback."""
        with self._lock:
            self._push_callback = callback

    def observe_async(self, turn_ref) -> bool:
        """Submit a turn evaluation task if this observer is still accepting work."""
        if isinstance(turn_ref, list):
            return self._observe_legacy_async(turn_ref)

        turn_id = ""
        if isinstance(turn_ref, dict):
            turn_id = str(turn_ref.get("turn_id") or "")
        elif turn_ref is not None:
            turn_id = str(turn_ref or "")
        return self._submit_turn_async(turn_id)

    def retry_failed_turn_evaluations(self, session_id: Optional[str] = None) -> int:
        """Submit retry tasks for failed structured turn evaluations in this session."""
        if not self.data_client or not hasattr(self.data_client, "list_interview_turns"):
            return 0

        target_session_id = session_id or self.session_id
        try:
            turns = self.data_client.list_interview_turns(target_session_id)
        except Exception:
            return 0

        submitted = 0
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            if turn.get("status") != "evaluation_failed":
                continue
            if not (turn.get("answer_text") or "").strip():
                continue
            if self._submit_turn_async(str(turn.get("turn_id") or ""), retry=True):
                submitted += 1
        return submitted

    def _submit_turn_async(self, turn_id: str, *, retry: bool = False) -> bool:
        if not turn_id or not self.data_client:
            return False

        key = f"turn:{turn_id}"
        with self._lock:
            if self._shutdown or not self._accepting:
                return False
            if key in self._pending_turns or (turn_id in self._completed_turn_ids and not retry):
                return False
            if retry:
                self._completed_turn_ids.discard(turn_id)
            self._pending_turns.add(key)

        try:
            future = self._executor.submit(self._observe_turn_safe, turn_id, key)
        except RuntimeError:
            with self._lock:
                self._pending_turns.discard(key)
            return False

        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._on_future_done)
        return True

    def _observe_legacy_async(self, chat_history: List[Dict]) -> bool:
        turn = len(chat_history) // 2
        key = f"legacy:{turn}"
        with self._lock:
            if self._shutdown or not self._accepting:
                return False
            if turn <= 0 or turn <= self.draft["last_turn"] or key in self._pending_turns:
                return False
            self._pending_turns.add(key)

        try:
            future = self._executor.submit(self._observe_legacy_safe, turn, key, list(chat_history))
        except RuntimeError:
            with self._lock:
                self._pending_turns.discard(key)
            return False

        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._on_future_done)
        return True

    def _on_future_done(self, future) -> None:
        with self._lock:
            self._futures.discard(future)

    def _observe_legacy_safe(self, turn: int, key: str, chat_history: List[Dict]) -> None:
        if self._shutdown:
            with self._lock:
                self._pending_turns.discard(key)
            return
        try:
            self._observe_legacy(turn, chat_history)
        except Exception as e:
            print(f"[EvalObserver] 未捕获异常：{e}")
        finally:
            with self._lock:
                self._pending_turns.discard(key)

    def _observe_turn_safe(self, turn_id: str, key: str) -> None:
        if self._shutdown:
            with self._lock:
                self._pending_turns.discard(key)
            return
        try:
            self._observe_turn(turn_id)
        except Exception as e:
            print(f"[EvalObserver] turn_id {turn_id} 未捕获异常：{e}")
        finally:
            with self._lock:
                self._pending_turns.discard(key)

    def _observe_legacy(self, turn: int, chat_history: List[Dict]) -> None:
        with self._lock:
            if self._shutdown or turn <= self.draft["last_turn"]:
                return

        last_q, last_a = "", ""
        for message in reversed(chat_history):
            if not last_a and message["role"] == "user":
                last_a = message["content"][:400]
            elif not last_q and message["role"] == "assistant":
                last_q = message["content"][:300]
            if last_q and last_a:
                break

        if not last_a:
            return

        prompt = (
            "你是面试评估观察员，只分析本轮对话片段，输出简洁 JSON。\n\n"
            f"面试官问：{last_q}\n"
            f"候选人答：{last_a}\n\n"
            "请输出（每条不超过15字，无则为 null）：\n"
            '{"strength": "本轮亮点或 null", "weakness": "本轮不足或 null", "note": "一句话关键观察"}'
        )

        try:
            raw = self.llm_client.generate([
                {"role": "system", "content": "你是简洁的面试评估观察员，只输出 JSON，不输出其他内容。"},
                {"role": "user", "content": prompt},
            ])
            match = re.search(r"\{[^{}]+\}", raw)
            if not match:
                print(f"[EvalObserver] turn {turn} 未解析到 JSON，raw={raw[:100]}")
                return
            obs = json.loads(match.group())
        except Exception as e:
            print(f"[EvalObserver] turn {turn} LLM 分析失败: {e}")
            return

        with self._lock:
            if self._shutdown or turn <= self.draft["last_turn"]:
                return
            if obs.get("strength"):
                self.draft["strengths"].append({"turn": turn, "text": obs["strength"]})
            if obs.get("weakness"):
                self.draft["weaknesses"].append({"turn": turn, "text": obs["weakness"]})
            if obs.get("note"):
                self.draft["turn_notes"].append({"turn": turn, "note": obs["note"]})
            self.draft["last_turn"] = turn
            snapshot = {
                "strengths": list(self.draft["strengths"]),
                "weaknesses": list(self.draft["weaknesses"]),
                "turn_notes": list(self.draft["turn_notes"]),
                "last_turn": self.draft["last_turn"],
            }
            push_callback = self._push_callback

        print(
            f"[EvalObserver] turn {turn} 草稿更新："
            f"strength={obs.get('strength')}, weakness={obs.get('weakness')}"
        )

        self._push_eval_update(turn, {
            "strength": obs.get("strength"),
            "weakness": obs.get("weakness"),
            "note": obs.get("note"),
        }, push_callback=push_callback)

        if self.data_client:
            try:
                ok = self.data_client.save_eval_draft(self.session_id, snapshot)
                if not ok:
                    print(f"[EvalObserver] turn {turn} 存储同步返回失败")
            except Exception as e:
                print(f"[EvalObserver] turn {turn} 存储同步异常: {e}")

    def _observe_turn(self, turn_id: str) -> None:
        turn = self.data_client.get_interview_turn(turn_id) if self.data_client else None
        if not turn:
            print(f"[EvalObserver] turn_id {turn_id} 不存在")
            return

        if turn.get("status") == "skipped":
            return

        turn_no = int(turn.get("turn_no") or 0)
        question = (turn.get("question_text") or "").strip()
        answer = (turn.get("answer_text") or "").strip()
        if not answer:
            return

        self._update_turn_status(turn_id, "evaluating")
        question_metadata = None
        try:
            question_metadata = self.data_client.get_question_metadata(turn_id)
        except Exception:
            question_metadata = None
        dimensions = []
        if isinstance(question_metadata, dict):
            dimensions = question_metadata.get("dimensions") or []
        dimensions = _normalize_dimensions(dimensions)
        observations = []

        for dimension_meta in dimensions[:2]:
            if self._is_shutdown():
                return
            dimension = dimension_meta["name"]
            prompt = _build_structured_eval_prompt(
                turn_no=turn_no,
                question=question,
                answer=answer,
                dimension_meta=dimension_meta,
            )

            try:
                raw = self.llm_client.generate([
                    {"role": "system", "content": "你是简洁的面试评估观察员，只输出 JSON，不输出其他内容。"},
                    {"role": "user", "content": prompt},
                ])
                match = re.search(r"\{[\s\S]*\}", raw)
                if not match:
                    print(f"[EvalObserver] turn {turn_no} {dimension} 未解析到 JSON，raw={raw[:100]}")
                    self._record_event(
                        "turn_evaluation_failed",
                        turn_id,
                        {"reason": "json_parse_failed", "dimension": dimension},
                    )
                    continue
                obs = json.loads(match.group())
            except Exception as e:
                print(f"[EvalObserver] turn {turn_no} {dimension} LLM 分析失败: {e}")
                self._record_event(
                    "turn_evaluation_failed",
                    turn_id,
                    {"reason": str(e)[:200], "dimension": dimension},
                )
                continue

            score = _coerce_score(obs.get("score"))
            pass_level = obs.get("pass_level") or _pass_level_from_score(score)
            evidence = obs.get("evidence") or obs.get("note") or ""
            suggestion = obs.get("suggestion") or ""
            normalized_obs = {
                "dimension": dimension,
                "score": score,
                "pass_level": pass_level,
                "evidence": evidence,
                "suggestion": suggestion,
                "strength": obs.get("strength"),
                "weakness": obs.get("weakness"),
                "note": obs.get("note") or evidence,
            }
            observations.append(normalized_obs)

            if hasattr(self.data_client, "upsert_turn_evaluation"):
                self.data_client.upsert_turn_evaluation(
                    session_id=self.session_id,
                    turn_id=turn_id,
                    turn_no=turn_no,
                    dimension=dimension,
                    score=score,
                    pass_level=pass_level,
                    evidence=evidence,
                    suggestion=suggestion,
                    evaluator_version="eval_observer_v1",
                )

        if not observations:
            self._update_turn_status(turn_id, "evaluation_failed")
            self._record_event(
                "turn_evaluation_failed",
                turn_id,
                {"reason": "no_dimension_evaluated", "dimension_count": len(dimensions[:2])},
            )
            return

        primary_obs = observations[0]

        with self._lock:
            if self._shutdown:
                return
            if primary_obs.get("strength"):
                self.draft["strengths"].append({"turn": turn_no, "text": primary_obs["strength"]})
            if primary_obs.get("weakness"):
                self.draft["weaknesses"].append({"turn": turn_no, "text": primary_obs["weakness"]})
            note = primary_obs.get("note") or primary_obs.get("evidence")
            if note:
                self.draft["turn_notes"].append({"turn": turn_no, "note": note})
            self.draft["last_turn"] = max(int(self.draft.get("last_turn") or 0), turn_no)
            self._completed_turn_ids.add(turn_id)
            snapshot = {
                "strengths": list(self.draft["strengths"]),
                "weaknesses": list(self.draft["weaknesses"]),
                "turn_notes": list(self.draft["turn_notes"]),
                "last_turn": self.draft["last_turn"],
            }
            push_callback = self._push_callback

        print(
            f"[EvalObserver] turn {turn_no} 结构化草稿更新："
            f"dimensions={len(observations)}, score={primary_obs.get('score')}, "
            f"strength={primary_obs.get('strength')}, weakness={primary_obs.get('weakness')}"
        )

        self._push_eval_update(turn_no, {
            "strength": primary_obs.get("strength"),
            "weakness": primary_obs.get("weakness"),
            "note": primary_obs.get("note") or primary_obs.get("evidence"),
            "dimensions": [
                {
                    "dimension": item.get("dimension"),
                    "score": item.get("score"),
                    "pass_level": item.get("pass_level"),
                }
                for item in observations
            ],
        }, push_callback=push_callback)

        self._update_turn_status(turn_id, "evaluated")

        try:
            ok = self.data_client.save_eval_draft(self.session_id, snapshot)
            if not ok:
                print(f"[EvalObserver] turn {turn_no} 存储同步返回失败")
        except Exception as e:
            print(f"[EvalObserver] turn {turn_no} 存储同步异常: {e}")

    def _record_event(self, event_type: str, turn_id: str, payload: dict) -> None:
        if not self.data_client or not hasattr(self.data_client, "record_agent_event"):
            return
        try:
            self.data_client.record_agent_event(
                self.session_id,
                event_type,
                turn_id=turn_id,
                agent_role="evaluator",
                payload=payload,
            )
        except Exception:
            return

    def _update_turn_status(self, turn_id: str, status: str) -> None:
        if not self.data_client or not hasattr(self.data_client, "update_interview_turn_status"):
            return
        try:
            self.data_client.update_interview_turn_status(turn_id, status)
        except Exception:
            return

    def _is_shutdown(self) -> bool:
        with self._lock:
            return bool(self._shutdown)

    def get_draft(self) -> Dict:
        with self._lock:
            return {
                "strengths": list(self.draft["strengths"]),
                "weaknesses": list(self.draft["weaknesses"]),
                "turn_notes": list(self.draft["turn_notes"]),
                "last_turn": self.draft["last_turn"],
            }

    def shutdown(self, wait: bool = False, timeout: Optional[float] = None) -> Dict:
        """
        Stop accepting new work and close the observer.

        When wait=True, already-submitted tasks are given a bounded chance to
        finish before the observer is frozen. After shutdown completes, no late
        task may mutate the draft anymore.
        """
        with self._lock:
            if self._shutdown:
                return {
                    "strengths": list(self.draft["strengths"]),
                    "weaknesses": list(self.draft["weaknesses"]),
                    "turn_notes": list(self.draft["turn_notes"]),
                    "last_turn": self.draft["last_turn"],
                }
            self._accepting = False
            futures = list(self._futures)

        not_done = set()
        if wait and futures:
            _, not_done = wait_futures(futures, timeout=timeout)
        else:
            not_done = {future for future in futures if not future.done()}

        with self._lock:
            self._shutdown = True
            self._push_callback = None

        for future in list(not_done):
            future.cancel()

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=False)

        print(f"[EvalObserver] session {self.session_id} 已关闭")
        return self.get_draft()

    def _push_eval_update(self, turn: int, eval_data: dict, push_callback=None) -> None:
        callback = push_callback if push_callback is not None else self._push_callback
        if callback:
            try:
                callback({
                    "type": "eval_update",
                    "turn": turn,
                    "data": eval_data,
                })
            except Exception as e:
                print(f"[EvalObserver] turn {turn} 推送失败：{e}")


def _normalize_dimensions(dimensions: List[Dict]) -> List[Dict]:
    result = []
    seen = set()
    for item in dimensions or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append({
            "name": name,
            "rubric": str(item.get("rubric") or DEFAULT_DIMENSION["rubric"]).strip(),
            "pass_criteria": str(item.get("pass_criteria") or DEFAULT_DIMENSION["pass_criteria"]).strip(),
        })
    return result or [dict(DEFAULT_DIMENSION)]


def _build_structured_eval_prompt(*, turn_no: int, question: str, answer: str, dimension_meta: Dict) -> str:
    return (
        "你是面试评估观察员，只分析本轮问答，输出 JSON。\n\n"
        f"轮次：{turn_no}\n"
        f"考察维度：{dimension_meta['name']}\n"
        f"评分标准：{dimension_meta['rubric']}\n"
        f"合格标准：{dimension_meta['pass_criteria']}\n\n"
        f"面试官问：{question[:600]}\n"
        f"候选人答：{answer[:900]}\n\n"
        "请输出："
        '{"dimension":"维度名","score":1-10,"pass_level":"excellent|pass|weak_pass|fail",'
        '"evidence":"一句证据","suggestion":"一句追问建议",'
        '"strength":"本轮亮点或 null","weakness":"本轮不足或 null","note":"一句话关键观察"}'
    )
