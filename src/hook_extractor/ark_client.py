"""火山方舟 / AI MediaKit 视频理解调用封装。

核心：走 Chat Completions 协议，content 里用 type=video_url 传公网视频 URL，
并在 video_url 对象内带 fps 控制抽帧率。MediaKit 端点（amk-ark...）与标准方舟
端点（ark...）共用该协议，仅 base_url 与鉴权 key 不同，因此这里统一实现。

参考：https://docs.volcengine.com/docs/82379/1895586 （视频理解）
      https://www.volcengine.com/docs/6448/2222229 （视频理解拓展工具 / MediaKit）
"""
from __future__ import annotations

import base64
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

    def analyze_clip(
        self,
        *,
        clip_path: str,
        prompt: str,
        meta_text: str,
        model: str,
        fps: float = 2.0,
        temperature: float = 0.1,
        timeout: float = 600.0,
    ) -> ExtractResult:
        """用 Pro 对本地剪出的片段做视频理解（片段以 base64 data URI 传入）。

        prompt 作为 system（片段分析提示词），meta_text 作为 user 文本（附带该片段的
        起止时间、人工研判颜色、原 hook_type/description 等）。
        """
        model_id = self.settings.resolve_model(model)
        with open(clip_path, "rb") as f:
            data_uri = "data:video/mp4;base64," + base64.b64encode(f.read()).decode()

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": data_uri, "fps": fps}},
                    {"type": "text", "text": meta_text},
                ],
            },
        ]
        try:
            resp = self.client.chat.completions.create(
                model=model_id, messages=messages, temperature=temperature, timeout=timeout
            )
        except Exception as e:  # noqa: BLE001
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
        # 兜底 1：截取第一个 { 到最后一个 }
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= s < e:
            try:
                return json.loads(cleaned[s : e + 1]), None
            except json.JSONDecodeError:
                pass
        # 兜底 2：输出被截断（如 max_tokens 用尽）时，抢救 hook / highlights 数组中
        # 已完整的对象——逐个匹配平衡花括号的对象再拼回，避免整条结果作废。
        salvaged = _salvage_truncated(cleaned)
        if salvaged is not None:
            return salvaged, "输出疑似被截断，已抢救部分完整条目"
        return None, "JSON 解析失败（可能被截断）"


def _salvage_truncated(text: str) -> dict | None:
    """从被截断的输出里抢救 highlights / hook 两个数组内已完整的对象。"""
    def extract_array(key: str) -> list[dict]:
        m = re.search(rf'"{key}"\s*:\s*\[', text)
        if not m:
            return []
        i = m.end()
        items: list[dict] = []
        n = len(text)
        while i < n:
            while i < n and text[i] in " \t\r\n,":
                i += 1
            if i >= n or text[i] == "]":
                break
            if text[i] != "{":
                break
            depth, j, in_str, esc = 0, i, False, False
            while j < n:
                c = text[j]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth != 0:  # 最后一个对象不完整，丢弃
                break
            try:
                items.append(json.loads(text[i : j + 1]))
            except json.JSONDecodeError:
                break
            i = j + 1
        return items

    hooks = extract_array("hook")
    highlights = extract_array("highlights")
    if not hooks and not highlights:
        return None
    return {"highlights": highlights, "hook": hooks}
