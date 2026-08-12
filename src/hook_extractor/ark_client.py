"""火山方舟 / AI MediaKit 视频理解调用封装。

核心：走 Chat Completions 协议，content 里用 type=video_url 传公网视频 URL，
并在 video_url 对象内带 fps 控制抽帧率。MediaKit 端点（amk-ark...）与标准方舟
端点（ark...）共用该协议，仅 base_url 与鉴权 key 不同，因此这里统一实现。

参考：https://docs.volcengine.com/docs/82379/1895586 （视频理解）
      https://www.volcengine.com/docs/6448/2222229 （视频理解拓展工具 / MediaKit）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from volcenginesdkarkruntime import Ark

from .config import Settings


@dataclass
class ExtractResult:
    raw_text: str                 # 模型原始输出
    parsed: dict | None           # 解析后的 JSON（失败为 None）
    model_id: str
    usage: dict | None
    error: str | None = None


class ArkVideoClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Ark(base_url=settings.base_url, api_key=settings.auth_key)

    def extract(
        self,
        *,
        video_url: str,
        prompt: str,
        model: str,
        fps: float,
        user_query: str = "请基于以上规则分析该视频，直接输出规定的 JSON。",
        temperature: float = 0.1,
        timeout: float = 1800.0,
    ) -> ExtractResult:
        """对单个视频跑一次提取。

        model 传别名或真实 Model ID 均可；temperature 默认调低以稳住时间戳输出。
        """
        model_id = self.settings.resolve_model(model)
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        # fps 放进 video_url 对象内，控制服务端抽帧率
                        "video_url": {"url": video_url, "fps": fps},
                    },
                    {"type": "text", "text": user_query},
                ],
            },
        ]

        try:
            resp = self.client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=temperature,
                timeout=timeout,
            )
        except Exception as e:  # noqa: BLE001 - 网络/鉴权/模型错误统一上抛给报表层
            return ExtractResult(
                raw_text="", parsed=None, model_id=model_id, usage=None, error=str(e)
            )

        text = resp.choices[0].message.content or ""
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else None
        parsed, perr = _parse_json(text)
        return ExtractResult(
            raw_text=text, parsed=parsed, model_id=model_id, usage=usage, error=perr
        )


def _parse_json(text: str) -> tuple[dict | None, str | None]:
    """容错解析：剥离 ```json 代码块围栏后再解析。"""
    if not text.strip():
        return None, "模型返回空内容"
    cleaned = text.strip()
    # 去掉 markdown 代码围栏
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError:
        # 兜底：截取第一个 { 到最后一个 }
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= s < e:
            try:
                return json.loads(cleaned[s : e + 1]), None
            except json.JSONDecodeError as err:
                return None, f"JSON 解析失败：{err}"
        return None, "未在输出中找到合法 JSON"
