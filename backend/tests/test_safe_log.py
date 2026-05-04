import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.safe_log import configure_stdio, safe_log
from core.tools import ocr_processing


class SafeLogTests(unittest.TestCase):
    def test_safe_log_handles_windows_gbk_clipboard_emoji(self):
        class FakeStdout:
            def __init__(self):
                self.encoding = "cp936"
                self.buffer = io.BytesIO()
                self.flushed = False

            def flush(self):
                self.flushed = True

        fake_stdout = FakeStdout()

        with patch("builtins.print", side_effect=UnicodeEncodeError("gbk", "📋", 0, 1, "encode error")):
            with patch.object(sys, "stdout", fake_stdout):
                safe_log("Prompt", "📋 系统提示词")

        payload = fake_stdout.buffer.getvalue()
        self.assertTrue(fake_stdout.flushed)
        self.assertIn(b"Prompt", payload)
        self.assertIn(b"\\U0001f4cb", payload)

    def test_ocr_safe_log_wrapper_handles_windows_gbk_clipboard_emoji(self):
        class FakeStdout:
            def __init__(self):
                self.encoding = "cp936"
                self.buffer = io.BytesIO()
                self.flushed = False

            def flush(self):
                self.flushed = True

        fake_stdout = FakeStdout()

        with patch("builtins.print", side_effect=UnicodeEncodeError("gbk", "📋", 0, 1, "encode error")):
            with patch.object(sys, "stdout", fake_stdout):
                ocr_processing._safe_log("OCR📋日志")

        payload = fake_stdout.buffer.getvalue()
        self.assertTrue(fake_stdout.flushed)
        self.assertIn(b"OCR", payload)
        self.assertIn(b"\\U0001f4cb", payload)

    def test_configure_stdio_prefers_utf8_with_backslashreplace(self):
        class ReconfigurableStream:
            def __init__(self):
                self.calls = []

            def reconfigure(self, **kwargs):
                self.calls.append(kwargs)

        fake_stdout = ReconfigurableStream()
        fake_stderr = ReconfigurableStream()

        with patch.object(sys, "stdout", fake_stdout):
            with patch.object(sys, "stderr", fake_stderr):
                configure_stdio()

        self.assertEqual(fake_stdout.calls, [{"encoding": "utf-8", "errors": "backslashreplace"}])
        self.assertEqual(fake_stderr.calls, [{"encoding": "utf-8", "errors": "backslashreplace"}])


if __name__ == "__main__":
    unittest.main()
