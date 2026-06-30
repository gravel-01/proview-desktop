import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.model_registry import get_default_provider, get_provider, init_providers


class ModelRegistryTests(unittest.TestCase):
    def test_ernie_default_uses_aistudio_supported_model_id(self):
        init_providers(
            deepseek_api_key="",
            ernie_api_key="ernie-key",
            ernie_base_url="https://aistudio.baidu.com/llm/lmapi/v3",
        )

        provider = get_provider("ernie")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.model, "ernie-4.5-turbo-128k")
        self.assertEqual(get_default_provider().model, "ernie-4.5-turbo-128k")

    def test_internal_ernie_is_unavailable_without_base_url(self):
        init_providers(
            deepseek_api_key="",
            ernie_api_key="",
            internal_ernie_base_url="",
        )

        provider = get_provider("internal-ernie")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.label, "内测大模型（未开放）")
        self.assertEqual(provider.model, "ERNIE-4.5-21B-A3B")
        self.assertEqual(provider.api_key, "internal")
        self.assertFalse(provider.available)

    def test_internal_ernie_is_available_with_base_url_and_no_real_api_key(self):
        init_providers(
            deepseek_api_key="",
            ernie_api_key="",
            internal_ernie_base_url="http://127.0.0.1/internal-ernie",
        )

        provider = get_provider("internal-ernie")
        self.assertIsNotNone(provider)
        self.assertTrue(provider.available)
        self.assertEqual(provider.base_url, "http://127.0.0.1/internal-ernie")
        self.assertEqual(provider.model, "ERNIE-4.5-21B-A3B")
        self.assertEqual(provider.api_key, "internal")

    def test_internal_ernie_uses_configured_model_name(self):
        init_providers(
            deepseek_api_key="",
            ernie_api_key="",
            internal_ernie_base_url="http://127.0.0.1/internal-ernie",
            internal_ernie_model="ERNIE-CUSTOM",
        )

        provider = get_provider("internal-ernie")
        self.assertIsNotNone(provider)
        self.assertTrue(provider.available)
        self.assertEqual(provider.model, "ERNIE-CUSTOM")


if __name__ == "__main__":
    unittest.main()
