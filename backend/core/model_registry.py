"""
模型注册表 — 集中管理所有 LLM 提供商的配置
新增模型只需在 PROVIDERS 字典中添加一项即可。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelProvider:
    """单个模型提供商的配置"""
    key: str            # 唯一标识，如 "deepseek", "ernie"
    label: str          # 前端展示名称
    model: str          # 模型 ID
    api_key: str        # API Key
    base_url: str       # API Base URL
    available: bool     # 是否可用（key 非空）


# 已注册的提供商（启动时由 init_providers() 填充）
_providers: dict[str, ModelProvider] = {}


def init_providers(
    deepseek_api_key: str = "",
    deepseek_base_url: str = "https://api.deepseek.com/v1",
    ernie_api_key: str = "",
    ernie_base_url: str = "https://aistudio.baidu.com/llm/lmapi/v3",
    internal_ernie_base_url: str = "",
    internal_ernie_model: str = "ERNIE-4.5-21B-A3B",
):
    """根据环境变量初始化所有提供商，应在 app 启动时调用一次。"""
    global _providers
    internal_ernie_base_url = (internal_ernie_base_url or "").strip()
    internal_ernie_model = (internal_ernie_model or "").strip() or "ERNIE-4.5-21B-A3B"
    _providers = {
        "deepseek": ModelProvider(
            key="deepseek",
            label="DeepSeek",
            model="deepseek-chat",
            api_key=deepseek_api_key or "",
            base_url=deepseek_base_url,
            available=bool(deepseek_api_key),
        ),
        "ernie": ModelProvider(
            key="ernie",
            label="文心一言",
            model="ernie-4.5-turbo-128k",
            api_key=ernie_api_key or "",
            base_url=ernie_base_url,
            available=bool(ernie_api_key),
        ),
        "ernie-thinking": ModelProvider(
            key="ernie-thinking",
            label="文心（深度思考）",
            model="ernie-5.0-thinking-preview",
            api_key=ernie_api_key or "",
            base_url=ernie_base_url,
            available=bool(ernie_api_key),
        ),
        "internal-ernie": ModelProvider(
            key="internal-ernie",
            label="内测大模型（未开放）",
            model=internal_ernie_model,
            api_key="internal",
            base_url=internal_ernie_base_url,
            available=bool(internal_ernie_base_url),
        ),
    }


def get_provider(key: str) -> Optional[ModelProvider]:
    """获取指定提供商配置，不存在返回 None。"""
    return _providers.get(key)


def get_default_provider() -> ModelProvider:
    """返回默认提供商（文心一言），若不可用则 fallback 到其他。"""
    default = _providers.get("ernie")
    if default and default.available:
        return default
    # fallback: deepseek 或第一个可用的
    ds = _providers.get("deepseek")
    if ds and ds.available:
        return ds
    for p in _providers.values():
        if p.available:
            return p
    # 全部不可用时返回 ernie（会在 Agent 层降级为 mock）
    return _providers.get("ernie", ModelProvider(
        key="ernie", label="文心一言", model="ernie-4.5-turbo-128k",
        api_key="", base_url="https://aistudio.baidu.com/llm/lmapi/v3", available=False
    ))


def list_available_providers() -> list[dict]:
    """返回前端可展示的提供商列表。"""
    return [
        {"key": p.key, "label": p.label, "available": p.available}
        for p in _providers.values()
    ]
