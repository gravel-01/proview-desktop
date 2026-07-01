import os
import shutil
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import model_registry


class ModelRegistryRefactorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(__file__).resolve().parent / ".codex_tmp_model_registry"
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.models_path = self.temp_dir / "models.json"
        self.env_path = self.temp_dir / ".env"
        self.env_path.write_text("", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _env(self, **extra):
        base = {
            "PROVIEW_DESKTOP_MODE": "1",
            "PROVIEW_MODELS_FILE": str(self.models_path),
            "PROVIEW_ENV_FILE": str(self.env_path),
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_BASE_URL": "",
            "ERNIE_API_KEY": "",
            "ERNIE_BASE_URL": "",
        }
        base.update(extra)
        return patch.dict(os.environ, base, clear=False)

    def _load_app_module_or_skip(self):
        try:
            import app as app_module
        except ModuleNotFoundError as exc:
            self.skipTest(f"route-level validation requires backend dependencies: {exc}")
        if hasattr(app_module, "_reload_runtime_config_state"):
            app_module._reload_runtime_config_state()
        return app_module

    class _CapturingDataClient:
        def __init__(self):
            self.sessions = []

        def get_user(self, _token):
            return None

        def get_or_create_local_user(self, username):
            return {"id": "local-user", "username": username}

        def create_session(self, **kwargs):
            self.sessions.append(kwargs)
            return True

    def test_legacy_env_migration_creates_models_json_once(self):
        with self._env(
            DEEPSEEK_API_KEY="sk-deepseek",
            ERNIE_API_KEY="sk-ernie",
        ):
            snapshot = model_registry.list_models(mask_secrets=False)

        self.assertTrue(self.models_path.exists())
        self.assertEqual(snapshot["default_model_id"], "ernie")
        self.assertEqual([item["id"] for item in snapshot["models"]], ["deepseek", "ernie", "ernie-thinking"])
        self.assertTrue(all(item["available"] for item in snapshot["models"]))
        self.assertEqual(snapshot["legacy_import"]["status"], "imported")
        self.assertEqual(snapshot["legacy_import"]["imported_count"], 3)
        self.assertEqual(snapshot["legacy_import"]["available_count"], 3)
        self.assertNotIn("sk-deepseek", str(snapshot["legacy_import"]))
        self.assertNotIn("sk-ernie", str(snapshot["legacy_import"]))

    def test_empty_legacy_env_records_not_found_import_summary(self):
        with self._env():
            snapshot = model_registry.list_models(mask_secrets=False)

        self.assertTrue(self.models_path.exists())
        self.assertEqual(snapshot["models"], [])
        self.assertEqual(snapshot["legacy_import"]["status"], "not_found")
        self.assertFalse(snapshot["legacy_import"]["legacy_config_found"])
        self.assertEqual(snapshot["legacy_import"]["imported_count"], 0)

    def test_existing_models_file_skips_legacy_env_import(self):
        self.models_path.write_text(
            """
{
  "version": 1,
  "default_model_id": "manual",
  "models": [
    {
      "id": "manual",
      "name": "Manual Model",
      "provider": "openai_compatible",
      "model": "manual-model",
      "base_url": "https://api.manual.example.com/v1",
      "api_key": "sk-manual",
      "enabled": true
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )

        with self._env(DEEPSEEK_API_KEY="sk-deepseek"):
            snapshot = model_registry.list_models(mask_secrets=False)

        self.assertEqual([item["id"] for item in snapshot["models"]], ["manual"])
        self.assertEqual(snapshot["legacy_import"]["status"], "skipped_existing_models_file")
        self.assertTrue(snapshot["legacy_import"]["existing_models_file"])
        self.assertTrue(snapshot["legacy_import"]["legacy_config_found"])
        self.assertNotIn("sk-deepseek", str(snapshot["legacy_import"]))

    def test_update_provider_keeps_existing_api_key_when_omitted(self):
        with self._env():
            created = model_registry.create_provider(
                {
                    "name": "Primary Interview Model",
                    "model": "gpt-4.1-mini",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "sk-existing",
                    "enabled": True,
                }
            )
            model_id = created["models"][0]["id"]

            model_registry.update_provider(
                model_id,
                {
                    "name": "Updated Interview Model",
                    "model": "gpt-4.1",
                    "base_url": "https://api.example.com/v1",
                    "enabled": True,
                },
            )
            provider = model_registry.get_provider(model_id)

        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "Updated Interview Model")
        self.assertEqual(provider.model, "gpt-4.1")
        self.assertEqual(provider.api_key, "sk-existing")

    def test_resolve_model_selection_prefers_requested_model_and_falls_back_to_default(self):
        with self._env():
            model_registry.create_provider(
                {
                    "name": "Primary Interview Model",
                    "model": "gpt-4.1-mini",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "sk-primary",
                    "enabled": True,
                }
            )["models"][0]
            secondary = model_registry.create_provider(
                {
                    "name": "Secondary Interview Model",
                    "model": "gpt-4.1",
                    "base_url": "https://api.backup.example.com/v1",
                    "api_key": "sk-secondary",
                    "enabled": True,
                }
            )["models"][1]
            model_registry.set_default_provider(secondary["id"])

            selected = model_registry.resolve_model_selection(secondary["id"])
            fallback = model_registry.resolve_model_selection("missing-model")

        self.assertEqual(selected.route, "session_selected")
        self.assertIsNotNone(selected.model)
        self.assertEqual(selected.model.id, secondary["id"])
        self.assertEqual(selected.requested_model_id, secondary["id"])

        self.assertEqual(fallback.route, "global_default")
        self.assertIsNotNone(fallback.model)
        self.assertEqual(fallback.model.id, secondary["id"])
        self.assertEqual(fallback.requested_model_id, "missing-model")

    def test_deleting_default_model_promotes_next_available_model(self):
        with self._env():
            primary = model_registry.create_provider(
                {
                    "name": "Primary Interview Model",
                    "model": "gpt-4.1-mini",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "sk-primary",
                    "enabled": True,
                }
            )["models"][0]
            secondary = model_registry.create_provider(
                {
                    "name": "Secondary Interview Model",
                    "model": "gpt-4.1",
                    "base_url": "https://api.backup.example.com/v1",
                    "api_key": "sk-secondary",
                    "enabled": True,
                }
            )["models"][1]
            model_registry.set_default_provider(secondary["id"])

            snapshot = model_registry.delete_provider(secondary["id"])
            fallback = model_registry.resolve_model_selection("")

        self.assertEqual(snapshot["default_model_id"], primary["id"])
        self.assertIsNotNone(fallback.model)
        self.assertEqual(fallback.model.id, primary["id"])
        self.assertEqual(fallback.route, "global_default")

    def test_probe_model_connection_rejects_incomplete_config_without_network(self):
        provider = model_registry.ModelProvider(
            id="incomplete",
            name="Incomplete",
            provider="openai_compatible",
            model="",
            api_key="",
            base_url="",
            enabled=True,
        )

        result = model_registry.probe_model_connection(
            provider,
            client_factory=lambda *_args: self.fail("connection probe should not build a client"),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "model_not_configured")
        self.assertIn("api_key", result["missing_fields"])

    def test_probe_model_connection_redacts_secret_from_failure_message(self):
        provider = model_registry.ModelProvider(
            id="configured",
            name="Configured",
            provider="openai_compatible",
            model="gpt-4.1-mini",
            api_key="sk-secret-token-value",
            base_url="https://api.example.com/v1",
            enabled=True,
        )

        def failing_factory(_provider, _timeout):
            raise RuntimeError("request failed with sk-secret-token-value and Bearer abcdef123456")

        result = model_registry.probe_model_connection(provider, client_factory=failing_factory)

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "connection_failed")
        self.assertNotIn("sk-secret-token-value", result["message"])
        self.assertNotIn("abcdef123456", result["message"])

    def test_runtime_config_exposes_models_file_and_setup_blocks_without_model(self):
        with self._env():
            app_module = self._load_app_module_or_skip()
            client = app_module.app.test_client()
            runtime_response = client.get("/api/runtime-config")
            setup_response = client.post(
                "/api/setup",
                data={"job_title": "后端工程师"},
            )

        runtime_payload = runtime_response.get_json()
        setup_payload = setup_response.get_json()

        self.assertEqual(runtime_response.status_code, 200)
        self.assertEqual(runtime_payload["models_file_path"], str(self.models_path))
        self.assertEqual(runtime_payload["models"], [])
        self.assertEqual(runtime_payload["legacy_import"]["status"], "not_found")
        self.assertEqual(setup_response.status_code, 400)
        self.assertIn("没有可用模型", setup_payload["message"])

    def test_models_routes_cover_crud_and_default_selection(self):
        with self._env():
            app_module = self._load_app_module_or_skip()
            client = app_module.app.test_client()

            initial_response = client.get("/api/models")
            self.assertEqual(initial_response.status_code, 200)
            self.assertEqual(initial_response.get_json()["models"], [])

            first_response = client.post(
                "/api/models",
                json={
                    "model": {
                        "name": "Primary Interview Model",
                        "model": "gpt-4.1-mini",
                        "base_url": "https://api.example.com/v1",
                        "api_key": "sk-primary",
                        "enabled": True,
                    }
                },
            )
            self.assertEqual(first_response.status_code, 200)
            first_payload = first_response.get_json()
            first_model = first_payload["models"][0]
            self.assertEqual(first_payload["default_model_id"], first_model["id"])

            second_response = client.post(
                "/api/models",
                json={
                    "model": {
                        "name": "Secondary Interview Model",
                        "model": "gpt-4.1",
                        "base_url": "https://api.backup.example.com/v1",
                        "api_key": "sk-secondary",
                        "enabled": True,
                    }
                },
            )
            self.assertEqual(second_response.status_code, 200)
            second_payload = second_response.get_json()
            second_model = second_payload["models"][1]

            update_response = client.put(
                f"/api/models/{second_model['id']}",
                json={
                    "model": {
                        "name": "Updated Secondary Model",
                        "model": "gpt-4.1",
                        "base_url": "https://api.backup.example.com/v1",
                        "enabled": True,
                    }
                },
            )
            self.assertEqual(update_response.status_code, 200)
            updated_model = next(item for item in update_response.get_json()["models"] if item["id"] == second_model["id"])
            self.assertEqual(updated_model["name"], "Updated Secondary Model")
            self.assertTrue(updated_model["api_key_configured"])
            self.assertEqual(model_registry.get_provider(second_model["id"]).api_key, "sk-secondary")

            default_response = client.post(f"/api/models/{second_model['id']}/default")
            self.assertEqual(default_response.status_code, 200)
            self.assertEqual(default_response.get_json()["default_model_id"], second_model["id"])

            delete_response = client.delete(f"/api/models/{second_model['id']}")
            self.assertEqual(delete_response.status_code, 200)
            delete_payload = delete_response.get_json()
            self.assertEqual(delete_payload["default_model_id"], first_model["id"])
            self.assertEqual([item["id"] for item in delete_payload["models"]], [first_model["id"]])

    def test_model_probe_route_returns_sanitized_probe_result(self):
        with self._env():
            app_module = self._load_app_module_or_skip()
            client = app_module.app.test_client()

            created = client.post(
                "/api/models",
                json={
                    "model": {
                        "name": "Probe Model",
                        "model": "gpt-4.1-mini",
                        "base_url": "https://api.example.com/v1",
                        "api_key": "sk-route-secret-value",
                        "enabled": True,
                    }
                },
            ).get_json()
            model_id = created["models"][0]["id"]

            with patch.object(
                app_module,
                "probe_model_connection",
                return_value={
                    "ok": False,
                    "code": "connection_failed",
                    "message": "连接测试失败，请检查配置。",
                    "latency_ms": 12,
                },
            ):
                response = client.post(f"/api/models/{model_id}/probe")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["model_id"], model_id)
            self.assertFalse(payload["probe"]["ok"])
            self.assertNotIn("sk-route-secret-value", str(payload))

    def test_setup_session_metadata_records_selected_model_snapshot(self):
        with self._env():
            first = model_registry.create_provider(
                {
                    "name": "Primary Interview Model",
                    "model": "gpt-4.1-mini",
                    "base_url": "https://api.example.com/v1",
                    "api_key": "sk-primary",
                    "enabled": True,
                }
            )["models"][0]
            second = model_registry.create_provider(
                {
                    "name": "Secondary Interview Model",
                    "model": "gpt-4.1",
                    "base_url": "https://api.backup.example.com/v1",
                    "api_key": "sk-secondary",
                    "enabled": True,
                }
            )["models"][1]
            model_registry.set_default_provider(first["id"])

            app_module = self._load_app_module_or_skip()
            client = app_module.app.test_client()
            capture = self._CapturingDataClient()
            with (
                patch.object(app_module, "STORAGE_AVAILABLE", True),
                patch.object(app_module, "data_client", capture),
                patch.object(app_module, "get_agent", return_value=None),
                patch.object(app_module, "_append_visible_message", return_value=None),
                patch.object(app_module, "_create_pending_turn", return_value=None),
            ):
                selected_response = client.post(
                    "/api/setup",
                    data={"job_title": "后端工程师", "model_id": second["id"]},
                )
                fallback_response = client.post(
                    "/api/setup",
                    data={"job_title": "后端工程师", "model_id": "missing-model"},
                )

        self.assertEqual(selected_response.status_code, 200)
        self.assertEqual(fallback_response.status_code, 200)
        self.assertEqual(len(capture.sessions), 2)

        selected_metadata = capture.sessions[0]["metadata"]
        self.assertEqual(selected_metadata["model_route"], "session_selected")
        self.assertEqual(selected_metadata["requested_model_id"], second["id"])
        self.assertEqual(selected_metadata["selected_model_id"], second["id"])
        self.assertEqual(selected_metadata["model_snapshot"]["model_id"], second["id"])
        self.assertEqual(selected_metadata["model_snapshot"]["model_snapshot"], "gpt-4.1")
        self.assertEqual(selected_metadata["model_snapshot"]["base_url_snapshot"], "https://api.backup.example.com/v1")

        fallback_metadata = capture.sessions[1]["metadata"]
        self.assertEqual(fallback_metadata["model_route"], "global_default")
        self.assertEqual(fallback_metadata["requested_model_id"], "missing-model")
        self.assertEqual(fallback_metadata["selected_model_id"], first["id"])
        self.assertEqual(fallback_metadata["model_snapshot"]["model_id"], first["id"])

    def test_prompt_generator_uses_session_agent_model_configuration(self):
        with self._env():
            app_module = self._load_app_module_or_skip()
            app_module._prompt_generators.clear()

            fake_prompt_module = types.ModuleType("core.prompt_generator")
            created = {}

            class FakePromptGenerator:
                def __init__(self, *, api_key, base_url, model):
                    created["api_key"] = api_key
                    created["base_url"] = base_url
                    created["model"] = model

                def generate(self, **_kwargs):
                    return "generated prompt"

            fake_prompt_module.PromptGenerator = FakePromptGenerator
            agent = types.SimpleNamespace(
                api_key="sk-session",
                base_url="https://api.session.example.com/v1",
                model_name="session-model",
            )

            with patch.dict(sys.modules, {"core.prompt_generator": fake_prompt_module}):
                generated = app_module._try_generate_prompt(
                    agent,
                    "后端工程师",
                    "technical",
                    "mid",
                    "strict",
                    "",
                    "",
                )

        self.assertEqual(generated, "generated prompt")
        self.assertEqual(created["api_key"], "sk-session")
        self.assertEqual(created["base_url"], "https://api.session.example.com/v1")
        self.assertEqual(created["model"], "session-model")


if __name__ == "__main__":
    unittest.main()
