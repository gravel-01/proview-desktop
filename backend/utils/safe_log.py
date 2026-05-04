"""Console logging helpers that do not crash on legacy Windows encodings."""

from __future__ import annotations

import sys
from typing import TextIO


def configure_stdio(encoding: str = "utf-8") -> None:
    """Prefer UTF-8 stdout/stderr, while keeping older Python streams usable."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue

        try:
            reconfigure(encoding=encoding, errors="backslashreplace")
        except Exception:
            # Some packaged/redirected streams do not allow reconfiguration.
            pass


def safe_log(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = True,
) -> None:
    """Print values without raising UnicodeEncodeError on GBK/CP936 consoles."""
    stream = file if file is not None else getattr(sys, "stdout", None)
    if stream is None:
        return

    text = sep.join(str(value) for value in values) + end
    try:
        print(text, end="", file=stream, flush=flush)
        return
    except UnicodeEncodeError:
        pass

    encoding = getattr(stream, "encoding", None) or "utf-8"
    payload = text.encode(encoding, errors="backslashreplace")

    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(payload)
    else:
        stream.write(payload.decode(encoding, errors="replace"))

    if flush:
        stream.flush()
