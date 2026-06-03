import io
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module


class ResumeParseApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_parse_resume_requires_file(self):
        response = self.client.post("/api/resume/parse", data={})
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["message"], "未上传文件")

    def test_parse_resume_returns_extraction_error(self):
        with patch.object(app_module, "ANALYZER_AVAILABLE", True), \
             patch.object(app_module, "_save_uploaded_resume", return_value=("resume.md", "/tmp/resume.md")), \
             patch.object(app_module, "_extract_resume_payload", return_value={
                 "success": False,
                 "text": "",
                 "reusable_text": "",
                 "raw_text": "",
                 "images": {},
                 "error_message": "解析失败",
             }):
            response = self.client.post(
                "/api/resume/parse",
                data={"file": (io.BytesIO(b"bad"), "resume.md")},
                content_type="multipart/form-data",
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["message"], "解析失败")

    def test_parse_resume_returns_builder_data(self):
        resume_text = "张三 Python 工程师 项目经历 负责系统开发，提升接口稳定性。" * 3
        builder_data = {
            "detectedTemplate": "tech",
            "basicInfo": {"name": "张三"},
            "modules": [],
        }
        analyzer = Mock()
        analyzer._extract_builder_data.return_value = builder_data

        with patch.object(app_module, "ANALYZER_AVAILABLE", True), \
             patch.object(app_module, "_save_uploaded_resume", return_value=("resume.md", "/tmp/resume.md")), \
             patch.object(app_module, "_extract_resume_payload", return_value={
                 "success": True,
                 "text": resume_text,
                 "reusable_text": resume_text,
                 "raw_text": resume_text,
                 "images": {},
                 "error_message": "",
             }), \
             patch.object(app_module, "ResumeAnalyzer", return_value=analyzer):
            response = self.client.post(
                "/api/resume/parse",
                data={"file": (io.BytesIO(b"resume"), "resume.md")},
                content_type="multipart/form-data",
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["basicInfo"]["name"], "张三")
        self.assertEqual(payload["data"]["detectedTemplate"], "tech")
        self.assertIn("张三 Python", payload["raw_text"])
        analyzer._extract_builder_data.assert_called_once_with(resume_text)


if __name__ == "__main__":
    unittest.main()
