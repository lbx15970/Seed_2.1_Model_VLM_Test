"""集中管理运行配置：读取 .env、cases.yaml，解析端点与鉴权。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# 项目根目录：src/hook_extractor/config.py -> 上溯三级
ROOT = Path(__file__).resolve().parents[2]

# 两套端点。默认 ark（标准方舟 v3，URL 视频 ≤50MB，本项目视频 43-45MB 够用）。
# mediakit 仅在视频超 50MB 时才需要（URL 上限 5GB，鉴权 key 需拼接 MediaKit Key）。
ENDPOINTS = {
    "ark": "https://ark.cn-beijing.volces.com/api/v3",
    "mediakit": "https://amk-ark.cn-beijing.volces.com/api/v1",
}


@dataclass
class Case:
    id: str
    name: str
    video_url: str


@dataclass
class Settings:
    ark_api_key: str
    mediakit_api_key: str
    endpoint: str
    base_url: str
    default_model: str
    default_fps: float
    models: dict[str, str] = field(default_factory=dict)
    cases: list[Case] = field(default_factory=list)

    @property
    def auth_key(self) -> str:
        """mediakit 端点要求 `方舟Key/MediaKitKey` 拼接鉴权；标准方舟只用方舟 Key。"""
        if self.endpoint == "mediakit":
            if not self.mediakit_api_key or self.mediakit_api_key.startswith("your_"):
                raise ValueError(
                    "endpoint=mediakit 需要在 .env 配置 MEDIAKIT_API_KEY；"
                    "本项目视频 <50MB，建议保持 ARK_ENDPOINT=ark。"
                )
            return f"{self.ark_api_key}/{self.mediakit_api_key}"
        return self.ark_api_key

    def resolve_model(self, alias_or_id: str) -> str:
        """支持传别名（seed-2-1-turbo）或直接传 Endpoint ID（ep-xxx）。"""
        return self.models.get(alias_or_id, alias_or_id)

    def get_case(self, case_id: str) -> Case:
        for c in self.cases:
            if c.id == case_id:
                return c
        raise KeyError(f"未找到 case: {case_id}，可用：{[c.id for c in self.cases]}")


def load_settings(cases_path: Path | None = None) -> Settings:
    load_dotenv(ROOT / ".env")

    ark_key = os.getenv("ARK_API_KEY", "")
    if not ark_key or ark_key.startswith("your_"):
        raise ValueError("请在 .env 配置真实 ARK_API_KEY（参考 .env.example）")

    endpoint = os.getenv("ARK_ENDPOINT", "ark").strip()
    if endpoint not in ENDPOINTS:
        raise ValueError(f"ARK_ENDPOINT 只能是 {list(ENDPOINTS)}，当前：{endpoint}")

    base_url = os.getenv("ARK_BASE_URL", "").strip() or ENDPOINTS[endpoint]

    cases_path = cases_path or (ROOT / "config" / "cases.yaml")
    with open(cases_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cases = [Case(**c) for c in raw.get("cases", [])]
    models = raw.get("models", {})

    return Settings(
        ark_api_key=ark_key,
        mediakit_api_key=os.getenv("MEDIAKIT_API_KEY", ""),
        endpoint=endpoint,
        base_url=base_url,
        default_model=os.getenv("DEFAULT_MODEL", "seed-2-1-turbo"),
        default_fps=float(os.getenv("DEFAULT_FPS", "2.0")),
        models=models,
        cases=cases,
    )
