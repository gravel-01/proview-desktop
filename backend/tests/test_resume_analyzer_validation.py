import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.resume_analyzer import ResumeAnalyzer


class ResumeAnalyzerValidationTests(unittest.TestCase):
    def test_validate_builder_data_normalizes_invalid_shapes(self):
        data = {
            "detectedTemplate": "unknown",
            "basicInfo": {"name": 123, "email": None},
            "modules": [
                "bad-module",
                {
                    "type": 456,
                    "visible": "yes",
                    "sortIndex": "bad",
                    "entries": [
                        "bad-entry",
                        {"orgName": 789, "isCurrent": "true"},
                    ],
                    "tags": ["Python", 42, ""],
                    "skillBars": [{"name": 123, "level": 120}, {"name": "Vue", "level": "bad"}],
                },
            ],
        }

        result = ResumeAnalyzer._validate_builder_data(data)

        self.assertEqual(result["detectedTemplate"], "classic")
        self.assertEqual(result["basicInfo"]["name"], "123")
        self.assertEqual(result["basicInfo"]["email"], "")
        self.assertIn("mobile", result["basicInfo"])
        self.assertEqual(len(result["modules"]), 1)

        module = result["modules"][0]
        self.assertTrue(module["id"].startswith("mod_"))
        self.assertEqual(module["type"], "456")
        self.assertTrue(module["visible"])
        self.assertEqual(module["sortIndex"], 1)
        self.assertEqual(module["tags"], ["Python", "42"])
        self.assertEqual(module["skillBars"][0]["level"], 100)
        self.assertEqual(module["skillBars"][1]["level"], 0)

        self.assertEqual(len(module["entries"]), 1)
        entry = module["entries"][0]
        self.assertTrue(entry["id"].startswith("ent_"))
        self.assertEqual(entry["orgName"], "789")
        self.assertTrue(entry["isCurrent"])
        self.assertEqual(entry["detail"], "")

    def test_validate_resume_suggestions_keeps_only_localizable_items(self):
        sections = [
            {
                "id": "sec_1",
                "type": "projects",
                "title": "项目经历",
                "content": "负责系统开发，提升接口稳定性。",
            }
        ]
        suggestions = [
            {
                "targetBlockId": "sec_1",
                "targetField": "content",
                "issueType": "BAD_TYPE",
                "issueLabel": "动词弱",
                "originalText": "负责系统开发",
                "suggestedText": "主导系统开发",
                "reason": "强化动词",
                "status": "ACCEPTED",
            },
            {
                "suggestionId": "missing-block",
                "targetBlockId": "sec_missing",
                "targetField": "content",
                "originalText": "负责系统开发",
                "suggestedText": "主导系统开发",
            },
            {
                "suggestionId": "missing-text",
                "targetBlockId": "sec_1",
                "targetField": "content",
                "originalText": "不存在的原文",
                "suggestedText": "主导系统开发",
            },
            {
                "suggestionId": "bad-field",
                "targetBlockId": "sec_1",
                "targetField": "title",
                "originalText": "负责系统开发",
                "suggestedText": "主导系统开发",
            },
        ]

        result = ResumeAnalyzer._validate_resume_suggestions(suggestions, sections)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["suggestionId"], "sug_001")
        self.assertEqual(result[0]["targetBlockId"], "sec_1")
        self.assertEqual(result[0]["targetField"], "content")
        self.assertEqual(result[0]["issueType"], "VAGUE_DESCRIPTION")
        self.assertEqual(result[0]["status"], "PENDING")

    def test_validate_builder_polish_converts_entry_fragment_to_full_field(self):
        modules = [
            {
                "id": "mod_1",
                "type": "project",
                "entries": [
                    {
                        "id": "ent_1",
                        "detail": "负责系统开发，提升接口稳定性。",
                    }
                ],
            }
        ]
        suggestions = [
            {
                "id": "sug_1",
                "moduleId": "mod_1",
                "entryId": "ent_1",
                "fieldPath": "detail",
                "originalText": "负责系统开发",
                "suggestedText": "主导系统开发",
                "reason": "强化动词",
            }
        ]

        result = ResumeAnalyzer.validate_builder_polish_suggestions(suggestions, modules)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["originalText"], "负责系统开发，提升接口稳定性。")
        self.assertEqual(result[0]["suggestedText"], "主导系统开发，提升接口稳定性。")
        self.assertEqual(result[0]["fieldPath"], "detail")
        self.assertEqual(result[0]["status"], "pending")

    def test_validate_builder_polish_filters_unsafe_items(self):
        modules = [
            {
                "id": "mod_1",
                "type": "project",
                "entries": [{"id": "ent_1", "detail": "负责系统开发。"}],
            }
        ]
        suggestions = [
            {"moduleId": "missing", "entryId": "ent_1", "fieldPath": "detail", "originalText": "负责", "suggestedText": "主导"},
            {"moduleId": "mod_1", "entryId": "missing", "fieldPath": "detail", "originalText": "负责", "suggestedText": "主导"},
            {"moduleId": "mod_1", "entryId": "ent_1", "fieldPath": "role", "originalText": "负责", "suggestedText": "主导"},
            {"moduleId": "mod_1", "entryId": "ent_1", "fieldPath": "detail", "originalText": "不存在", "suggestedText": "主导"},
            {"moduleId": "mod_1", "entryId": "ent_1", "fieldPath": "detail", "originalText": "负责", "suggestedText": ""},
        ]

        result = ResumeAnalyzer.validate_builder_polish_suggestions(suggestions, modules)

        self.assertEqual(result, [])

    def test_validate_builder_polish_keeps_content_replace_suggestion(self):
        modules = [{"id": "mod_2", "type": "custom", "content": "熟悉 Python 和 Vue。"}]
        suggestions = [
            {
                "moduleId": "mod_2",
                "fieldPath": "content",
                "originalText": "熟悉 Python",
                "suggestedText": "精通 Python",
                "reason": "突出技能",
            }
        ]

        result = ResumeAnalyzer.validate_builder_polish_suggestions(suggestions, modules)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["originalText"], "熟悉 Python")
        self.assertEqual(result[0]["suggestedText"], "精通 Python")
        self.assertIsNone(result[0]["entryId"])


if __name__ == "__main__":
    unittest.main()
