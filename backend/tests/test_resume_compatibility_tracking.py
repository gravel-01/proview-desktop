import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app as app_module
from core.tools import ocr_processing
from services.resume_text_extraction import (
    OCR_RESUME_EXTENSIONS,
    DIRECT_TEXT_EXTENSIONS,
    ResumeOcrUnavailableError,
    UnsupportedResumeFormatError,
    ensure_supported_resume_extension,
    extract_resume_content,
)


class ResumeFormatCompatibilityTests(unittest.TestCase):
    def test_supported_extensions_are_accepted(self):
        for ext in sorted(OCR_RESUME_EXTENSIONS | DIRECT_TEXT_EXTENSIONS):
            with self.subTest(ext=ext):
                self.assertEqual(ensure_supported_resume_extension(f"resume{ext}"), ext)

    def test_doc_extension_returns_upgrade_hint(self):
        with self.assertRaises(UnsupportedResumeFormatError) as ctx:
            ensure_supported_resume_extension("legacy_resume.doc")

        self.assertIn(".doc", str(ctx.exception))
        self.assertIn(".docx", str(ctx.exception))

    def test_pdf_requires_ocr_loader(self):
        temp_path = BACKEND_ROOT / "tests" / "__compat_resume_test__.pdf"
        try:
            temp_path.write_bytes(b"%PDF-1.4")
            with self.assertRaises(ResumeOcrUnavailableError):
                extract_resume_content(
                    str(temp_path),
                    include_images=False,
                    ocr_available=False,
                )
        finally:
            temp_path.unlink(missing_ok=True)


class OcrRuntimeCompatibilityTests(unittest.TestCase):
    def test_safe_log_handles_windows_gbk_encoding(self):
        class FakeStdout:
            def __init__(self):
                self.encoding = "cp936"
                self.buffer = io.BytesIO()
                self.flushed = False

            def flush(self):
                self.flushed = True

        fake_stdout = FakeStdout()

        with patch("builtins.print", side_effect=UnicodeEncodeError("gbk", "🙂", 0, 1, "encode error")):
            with patch.object(sys, "stdout", fake_stdout):
                ocr_processing._safe_log("OCR🙂日志")

        payload = fake_stdout.buffer.getvalue()
        self.assertTrue(fake_stdout.flushed)
        self.assertIn(b"OCR", payload)
        self.assertIn(b"\\U0001f642", payload)


class ResumeApiContractCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_resume_analyze_json_requires_ocr_text(self):
        with patch.object(app_module, "ANALYZER_AVAILABLE", True):
            response = self.client.post("/api/resume/analyze", json={"job_title": "后端"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["message"], "ocr_text 不能为空")

    def test_resume_analyze_json_returns_structured_payload(self):
        class AnalyzerStub:
            def __init__(self, api_key, base_url):
                self.api_key = api_key
                self.base_url = base_url

            def analyze(self, ocr_text, job_title, report_context=None):
                return {
                    "sections": [{"title": "概述", "content": "测试内容"}],
                    "suggestions": ["补充项目量化指标"],
                    "builder_data": {"name": "张三"},
                }

        with patch.object(app_module, "ANALYZER_AVAILABLE", True):
            with patch.object(app_module, "ResumeAnalyzer", AnalyzerStub):
                response = self.client.post(
                    "/api/resume/analyze",
                    json={"ocr_text": "候选人有 5 年后端经验", "job_title": "后端工程师"},
                )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertIn("token", payload)
        self.assertEqual(payload["images"], {})
        self.assertEqual(len(payload["sections"]), 1)

    def test_resume_analyze_form_rejects_legacy_doc(self):
        with patch.object(app_module, "ANALYZER_AVAILABLE", True):
            response = self.client.post(
                "/api/resume/analyze",
                data={"job_title": "后端", "resume": (io.BytesIO(b"fake-doc"), "legacy.doc")},
                content_type="multipart/form-data",
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn(".doc", payload["message"])

    def test_resume_library_serialization_exposes_preview_contract(self):
        with patch.object(
            app_module,
            "get_resume_preview_summary",
            return_value={
                "file_kind": "pdf",
                "preview_page_count": 2,
                "preview_paths": ["a.png", "b.png"],
                "has_preview": True,
            },
        ):
            payload = app_module._serialize_resume_library_record(
                {
                    "id": 42,
                    "file_name": "demo.pdf",
                    "file_path": "D:/tmp/demo.pdf",
                }
            )

        self.assertEqual(payload["file_kind"], "pdf")
        self.assertTrue(payload["can_preview"])
        self.assertEqual(payload["preview_cover_url"], "/api/my-resumes/42/preview/1")
        self.assertEqual(
            payload["preview_image_urls"],
            ["/api/my-resumes/42/preview/1", "/api/my-resumes/42/preview/2"],
        )


if __name__ == "__main__":
    unittest.main()

