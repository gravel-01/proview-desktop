from __future__ import annotations

import threading
import uuid
from typing import Dict, List, Optional

from services.question_metadata_extractor import DEFAULT_DIMENSION, QuestionMetadataExtractor


class InterviewTurnService:
    """Coordinate visible chat messages with structured interview turns."""

    def __init__(self, data_client=None):
        self.data_client = data_client
        self.metadata_extractor = QuestionMetadataExtractor()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def set_data_client(self, data_client) -> None:
        self.data_client = data_client

    def clear_session(self, session_id: str) -> None:
        with self._locks_guard:
            self._locks.pop(session_id, None)

    def supports_structured_turns(self) -> bool:
        return bool(self._capabilities().get("structured_turns"))

    def append_message(self, session_id: str, role: str, content: str) -> Optional[Dict]:
        if not self.data_client:
            return None
        if hasattr(self.data_client, "append_message"):
            return self.data_client.append_message(session_id, role, content)
        ok = self.data_client.save_message(session_id, role, content)
        if not ok:
            return None
        return {"id": None, "session_id": session_id, "role": role, "content": content, "timestamp": ""}

    def create_pending_turn(
        self,
        session_id: str,
        *,
        question_message: Optional[Dict],
        question_text: str,
        source: str = "interviewer_llm",
        question_type: str = "opening",
        difficulty: str = "",
        rag_candidates: Optional[List[Dict]] = None,
    ) -> Optional[Dict]:
        if not self.data_client or not self.supports_structured_turns() or not question_text:
            return None
        with self._session_lock(session_id):
            turn_no = self.data_client.get_next_turn_no(session_id)
            turn = self.data_client.create_interview_turn(
                session_id=session_id,
                turn_id=uuid.uuid4().hex,
                turn_no=turn_no,
                question_message_id=_message_id(question_message),
                question_text=question_text,
                status="pending",
            )
            if turn:
                self._save_default_question_metadata(
                    session_id=session_id,
                    turn=turn,
                    question_text=question_text,
                    source=source,
                    question_type=question_type,
                    difficulty=difficulty,
                    rag_candidates=rag_candidates or [],
                )
            return turn

    def answer_pending_turn(
        self,
        session_id: str,
        *,
        answer_message: Optional[Dict],
        answer_text: str,
    ) -> Optional[Dict]:
        if not self.data_client or not self.supports_structured_turns():
            return None
        with self._session_lock(session_id):
            pending = self.data_client.get_latest_pending_turn(session_id)
            if not pending:
                self.record_event(
                    session_id,
                    "missing_pending_turn",
                    payload={"answer_preview": (answer_text or "")[:120]},
                )
                turn_no = self.data_client.get_next_turn_no(session_id)
                recovery_turn = self.data_client.create_interview_turn(
                    session_id=session_id,
                    turn_id=uuid.uuid4().hex,
                    turn_no=turn_no,
                    question_message_id="",
                    question_text="",
                    status="pending",
                )
                if not recovery_turn:
                    return None
                pending = recovery_turn

            return self.data_client.answer_interview_turn(
                pending["turn_id"],
                answer_message_id=_message_id(answer_message),
                answer_text=answer_text,
            )

    def record_event(
        self,
        session_id: str,
        event_type: str,
        *,
        turn_id: str = "",
        agent_role: str = "interviewer",
        payload: Optional[Dict] = None,
    ) -> bool:
        if not self.data_client or not self._capabilities().get("agent_events"):
            return False
        return bool(
            self.data_client.record_agent_event(
                session_id,
                event_type,
                turn_id=turn_id,
                agent_role=agent_role,
                payload=payload or {},
            )
        )

    def _capabilities(self) -> Dict:
        if not self.data_client or not hasattr(self.data_client, "storage_capabilities"):
            return {}
        try:
            return self.data_client.storage_capabilities() or {}
        except Exception:
            return {}

    def _session_lock(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(session_id)
            if not lock:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock

    def _save_default_question_metadata(
        self,
        *,
        session_id: str,
        turn: Dict,
        question_text: str,
        source: str,
        question_type: str,
        difficulty: str,
        rag_candidates: Optional[List[Dict]] = None,
    ) -> None:
        if not self._capabilities().get("question_metadata"):
            return
        try:
            previous_metadata = self._get_previous_metadata(
                session_id=session_id,
                current_turn_no=int(turn.get("turn_no") or 0),
            )
            metadata = self.metadata_extractor.build(
                question_text=question_text,
                question_type=question_type,
                source=source,
                difficulty=difficulty,
                rag_candidates=rag_candidates or [],
                previous_metadata=previous_metadata,
            )
            self.data_client.save_question_metadata(
                session_id=session_id,
                turn_id=turn["turn_id"],
                turn_no=int(turn.get("turn_no") or 0),
                question_text=question_text,
                dimensions=metadata.get("dimensions") or [dict(DEFAULT_DIMENSION)],
                difficulty=metadata.get("difficulty") or difficulty,
                question_type=metadata.get("question_type") or question_type,
                source=metadata.get("source") or source,
                metadata_refs=metadata.get("metadata_refs") or [],
            )
        except Exception:
            self.record_event(
                session_id,
                "question_metadata_parse_failed",
                turn_id=turn.get("turn_id") or "",
                payload={"reason": "default_metadata_save_failed"},
            )

    def _get_previous_metadata(self, *, session_id: str, current_turn_no: int) -> Optional[Dict]:
        if current_turn_no <= 1 or not hasattr(self.data_client, "list_interview_turns"):
            return None
        try:
            turns = self.data_client.list_interview_turns(session_id)
            previous_turns = [
                item for item in turns
                if int(item.get("turn_no") or 0) < current_turn_no and item.get("turn_id")
            ]
            if not previous_turns:
                return None
            previous_turns.sort(key=lambda item: int(item.get("turn_no") or 0), reverse=True)
            return self.data_client.get_question_metadata(previous_turns[0]["turn_id"])
        except Exception:
            return None


def _message_id(message: Optional[Dict]) -> str:
    if not isinstance(message, dict):
        return ""
    value = message.get("id")
    return str(value) if value not in (None, "") else ""
