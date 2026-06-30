import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
TEST_FILES_ROOT = BACKEND_ROOT / "tests"

from core.tools import ocr_processing


class OcrProcessingTests(unittest.TestCase):
    def test_http_error_keeps_response_status_and_body(self):
        pdf_path = TEST_FILES_ROOT / f"__ocr_http_error_{uuid.uuid4().hex}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        class FakeResponse:
            status_code = 400
            text = '{"error":"bad request from ocr service"}'

            def __bool__(self):
                return False

            def raise_for_status(self):
                raise requests.exceptions.HTTPError("400 Client Error", response=self)

        try:
            with patch.object(ocr_processing, "get_ocr_runtime_settings", return_value=("https://ocr.example/layout", "token")):
                with patch.object(ocr_processing.requests, "post", return_value=FakeResponse()):
                    result = ocr_processing.perform_ocr(str(pdf_path), use_preprocessing=False)

            self.assertIn("HTTP 400", result)
            self.assertIn("bad request from ocr service", result)
        finally:
            pdf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
