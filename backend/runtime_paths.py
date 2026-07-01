from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "ProView-AI-Interviewer"
BACKEND_SOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(os.getenv("PROVIEW_RESOURCE_DIR") or getattr(sys, "_MEIPASS", BACKEND_SOURCE_DIR))


def _default_app_data_root() -> Path:
    if getattr(sys, "frozen", False):
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME
    return BACKEND_SOURCE_DIR


APP_DATA_ROOT = Path(os.getenv("PROVIEW_APP_DATA_DIR") or _default_app_data_root())


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_resource_path(*parts: str) -> Path:
    if not parts:
        return RESOURCE_ROOT
    return RESOURCE_ROOT.joinpath(*parts)


def get_app_data_path(*parts: str, is_dir: bool = False) -> Path:
    path = APP_DATA_ROOT.joinpath(*parts) if parts else APP_DATA_ROOT
    target = path if is_dir else path.parent
    ensure_directory(target)
    return path


def get_env_file_path() -> Path:
    override = (os.getenv("PROVIEW_ENV_FILE") or "").strip()
    if override:
        return Path(override)
    return get_resource_path(".env")


def get_models_file_path() -> Path:
    override = (os.getenv("PROVIEW_MODELS_FILE") or "").strip()
    if override:
        return Path(override)
    return get_app_data_path("models.json")
