"""
Optional Langfuse tracing helpers for LangChain execution.

Tracing must never block the interview flow: missing dependencies,
missing environment variables, or SDK initialization failures all degrade
to running without callbacks.
"""
import os
from typing import Any, Optional

_LANGFUSE_CLIENT_INITIALIZED = False
_LANGFUSE_CLIENT_INIT_FAILED = False
_LANGFUSE_INIT_ERROR: Optional[Exception] = None


def _build_usage_enriching_handler(callback_handler_cls):
    class UsageEnrichingCallbackHandler(callback_handler_cls):
        def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
            _enrich_llm_result_usage(response)
            return super().on_llm_end(
                response,
                run_id=run_id,
                parent_run_id=parent_run_id,
                **kwargs,
            )

    return UsageEnrichingCallbackHandler


def _read_env(key: str) -> str:
    value = os.getenv(key)
    return str(value).strip() if value is not None else ""


def _ensure_langfuse_client_initialized(
    *,
    public_key: str,
    secret_key: str,
    base_url: str,
) -> bool:
    """Initialize the Langfuse v4 client once per process."""
    global _LANGFUSE_CLIENT_INITIALIZED
    global _LANGFUSE_CLIENT_INIT_FAILED
    global _LANGFUSE_INIT_ERROR

    if _LANGFUSE_CLIENT_INITIALIZED:
        return True
    if _LANGFUSE_CLIENT_INIT_FAILED:
        return False

    try:
        from langfuse import Langfuse

        try:
            Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=base_url,
            )
        except TypeError:
            Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=base_url,
            )
        _LANGFUSE_CLIENT_INITIALIZED = True
        return True
    except Exception as exc:
        _LANGFUSE_CLIENT_INIT_FAILED = True
        _LANGFUSE_INIT_ERROR = exc
        return False


def get_langfuse_callback_handler() -> Optional[Any]:
    """Create a Langfuse LangChain callback handler when configured."""
    secret_key = _read_env("LANGFUSE_SECRET_KEY")
    public_key = _read_env("LANGFUSE_PUBLIC_KEY")
    base_url = _read_env("LANGFUSE_BASE_URL")

    if not secret_key or not public_key or not base_url:
        return None

    try:
        from langfuse.langchain import CallbackHandler
    except Exception:
        try:
            from langfuse.callback import CallbackHandler
        except Exception:
            return None

    Handler = _build_usage_enriching_handler(CallbackHandler)

    try:
        return Handler(
            secret_key=secret_key,
            public_key=public_key,
            host=base_url,
        )
    except TypeError:
        if not _ensure_langfuse_client_initialized(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
        ):
            return None

        try:
            return Handler(public_key=public_key)
        except TypeError:
            try:
                return Handler()
            except Exception:
                return None
        except Exception:
            return None
    except Exception:
        return None


def merge_langfuse_callback_config(
    config: Optional[dict] = None,
    trace_context: Optional[dict] = None,
) -> Optional[dict]:
    """
    Return a LangChain Runnable config with Langfuse appended to callbacks.

    Existing callbacks are preserved. If Langfuse is unavailable, the original
    config is returned unchanged so callers can pass it through safely.
    """
    handler = get_langfuse_callback_handler()
    if handler is None:
        return config

    merged = dict(config or {})
    existing_callbacks = merged.get("callbacks") or []
    if isinstance(existing_callbacks, list):
        callbacks = [*existing_callbacks, handler]
    else:
        callbacks = [existing_callbacks, handler]
    merged["callbacks"] = callbacks
    _merge_trace_context(merged, trace_context)
    return merged


def _merge_trace_context(config: dict, trace_context: Optional[dict]) -> None:
    if not isinstance(trace_context, dict):
        return

    metadata = dict(config.get("metadata") or {})
    tags = _as_string_list(config.get("tags"))
    trace_tags = _as_string_list(trace_context.get("tags"))

    for tag in trace_tags:
        if tag not in tags:
            tags.append(tag)

    session_id = _clean_trace_value(trace_context.get("session_id"))
    user_id = _clean_trace_value(trace_context.get("user_id"))
    trace_name = _clean_trace_value(trace_context.get("trace_name"))

    if session_id:
        metadata.setdefault("langfuse_session_id", session_id)
        metadata.setdefault("proview_session_id", session_id)
    if user_id:
        metadata.setdefault("langfuse_user_id", user_id)
    if trace_name:
        metadata.setdefault("langfuse_trace_name", trace_name)

    existing_langfuse_tags = _as_string_list(metadata.get("langfuse_tags"))
    for tag in [*tags, *trace_tags]:
        if tag not in existing_langfuse_tags:
            existing_langfuse_tags.append(tag)
    if existing_langfuse_tags:
        metadata["langfuse_tags"] = existing_langfuse_tags

    context_metadata = trace_context.get("metadata")
    if isinstance(context_metadata, dict):
        for key, value in context_metadata.items():
            if _is_safe_metadata_value(value):
                metadata.setdefault(str(key), value)

    if metadata:
        config["metadata"] = metadata
    if tags:
        config["tags"] = tags


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]

    result = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _clean_trace_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_safe_metadata_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, tuple)):
        return all(isinstance(item, (str, int, float, bool)) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and isinstance(item, (str, int, float, bool))
            for key, item in value.items()
        )
    return False


def _enrich_llm_result_usage(response: Any) -> None:
    """Normalize provider-specific LangChain usage metadata for Langfuse."""
    usage = _extract_usage_from_llm_result(response)
    model = _extract_model_from_llm_result(response)

    if usage is None and model is None:
        return

    try:
        if getattr(response, "llm_output", None) is None:
            response.llm_output = {}
        if usage is not None:
            response.llm_output.setdefault("token_usage", usage)
            response.llm_output.setdefault("usage", usage)
        if model:
            response.llm_output.setdefault("model_name", model)
    except Exception:
        return


def _extract_usage_from_llm_result(response: Any) -> Optional[dict]:
    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, dict):
        for key in ("token_usage", "usage", "usage_metadata"):
            usage = _normalize_usage(llm_output.get(key))
            if usage:
                return usage

    for generation in getattr(response, "generations", []) or []:
        for chunk in generation or []:
            for source in _iter_generation_usage_sources(chunk):
                usage = _normalize_usage(source)
                if usage:
                    return usage
    return None


def _extract_model_from_llm_result(response: Any) -> Optional[str]:
    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, dict):
        for key in ("model_name", "model", "model_id", "modelId"):
            value = llm_output.get(key)
            if value:
                return str(value)

    for generation in getattr(response, "generations", []) or []:
        for chunk in generation or []:
            for source in _iter_generation_model_sources(chunk):
                if source:
                    return str(source)
    return None


def _iter_generation_usage_sources(chunk: Any):
    generation_info = getattr(chunk, "generation_info", None)
    if isinstance(generation_info, dict):
        for key in ("usage_metadata", "token_usage", "usage"):
            yield generation_info.get(key)

    message = getattr(chunk, "message", None)
    if message is None:
        return

    yield getattr(message, "usage_metadata", None)

    response_metadata = getattr(message, "response_metadata", None)
    if isinstance(response_metadata, dict):
        for key in ("usage_metadata", "token_usage", "usage"):
            yield response_metadata.get(key)

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        for key in ("usage_metadata", "token_usage", "usage"):
            yield additional_kwargs.get(key)


def _iter_generation_model_sources(chunk: Any):
    generation_info = getattr(chunk, "generation_info", None)
    if isinstance(generation_info, dict):
        for key in ("model_name", "model", "model_id", "modelId"):
            yield generation_info.get(key)

    message = getattr(chunk, "message", None)
    if message is None:
        return

    response_metadata = getattr(message, "response_metadata", None)
    if isinstance(response_metadata, dict):
        for key in ("model_name", "model", "model_id", "modelId"):
            yield response_metadata.get(key)

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        for key in ("model_name", "model", "model_id", "modelId"):
            yield additional_kwargs.get(key)


def _normalize_usage(value: Any) -> Optional[dict]:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    elif hasattr(value, "dict"):
        value = value.dict()
    elif hasattr(value, "__dict__") and not isinstance(value, dict):
        value = value.__dict__
    if not isinstance(value, dict):
        return None

    normalized = dict(value)
    alias_map = {
        "input_tokens": "prompt_tokens",
        "output_tokens": "completion_tokens",
        "input": "prompt_tokens",
        "output": "completion_tokens",
        "total": "total_tokens",
    }
    for source, target in alias_map.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]

    has_usage = any(
        key in normalized
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "input",
            "output",
            "total",
        )
    )
    return normalized if has_usage else None
