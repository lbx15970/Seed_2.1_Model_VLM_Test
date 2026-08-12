"""片段分析器：自动化迭代的核心环节。

流程：
  1) 从 eval 结果里拿到 badcase（绿色漏保留 / 红色误命中）；
  2) 用 ffmpeg 从原视频 URL 按 [start,end]（带 padding）剪出小片段（480p、低码率）；
  3) 片段以 base64 传给 Seed 2.1 Pro + 「片段视频分析提示词」，做视频理解；
  4) Pro 产出结构化判定：keep/drop、三力检验、命中的 badcase 编号、
     以及最关键的 prompt_improvement（提示词该怎么改）。

Pro 只做视频理解，不做时间戳提取。片段分析提示词见 prompts/segment_analysis.txt。
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .ark_client import ArkVideoClient
from .config import ROOT, Settings
from .evaluator import _iou


@dataclass
class BadCase:
    """一个需要片段分析的 badcase。"""
    case_id: str
    case_name: str
    video_url: str
    bench_id: str
    quality: str            # good=本应保留却被删 / bad=本应删除却被留
    kind: str               # "green_missed"（漏保留） / "red_kept"（误命中）
    start_ms: int
    end_ms: int
    content: str            # benchmark 里该片段的人工描述
    pred_hook: dict | None = None   # 若是 red_kept，附上模型当时输出的那条 hook


@dataclass
class SegmentVerdict:
    bad: BadCase
    clip_path: str
    analysis: dict | None
    raw_text: str
    error: str | None = None


def cut_clip(video_url: str, start_ms: int, end_ms: int, out_path: Path,
             pad_ms: int = 3000, height: int = 480) -> None:
    """用 ffmpeg 从远程 URL 剪片段。前后各加 pad 便于理解上下文，尾部 padding 更长。

    尾部多留 pad 是刻意的：hook 的关键在"结束点之后有没有答案"，让 Pro 能看到
    紧随其后的一两秒，从而判断是否"截晚了/答案已泄露"。
    """
    start_s = max(0, (start_ms - pad_ms)) / 1000.0
    dur_s = (end_ms - start_ms + 2 * pad_ms) / 1000.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", f"{start_s:.3f}", "-t", f"{dur_s:.3f}",
        "-i", video_url,
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "64k",
        str(out_path), "-loglevel", "error",
    ]
    subprocess.run(cmd, check=True, timeout=180)


def _meta_text(bad: BadCase, pad_ms: int) -> str:
    human = "good（人工研判：本应保留的优质 hook）" if bad.quality == "good" \
        else "bad（人工研判：本应删除的 badcase）"
    lines = [
        "<元信息>",
        f"- 该片段取自短剧《{bad.case_name}》。",
        f"- 片段在原视频中的时间：{bad.start_ms}ms ~ {bad.end_ms}ms"
        f"（本片段前后各多剪了约 {pad_ms}ms 作为上下文，真正的钩子结束点在片段的中后段）。",
        f"- 人工研判颜色：{human}。",
    ]
    if bad.content:
        lines.append(f"- 人工对该片段的描述：{bad.content}")
    if bad.pred_hook:
        lines.append(
            f"- hook 提取模型当时把它判为 hook，类型={bad.pred_hook.get('hook_type')}，"
            f"理由/描述={bad.pred_hook.get('description') or bad.pred_hook.get('end_point_reason')}"
        )
    lines.append(
        "请按系统提示词的 7 步分析这个片段，重点判断它作为短视频结尾钩子是否成立，"
        "并给出可执行的 hook 提取提示词改进建议。严格输出规定的 JSON。"
    )
    return "\n".join(lines)


def collect_badcases(
    run_dir: Path,
    benchmark: dict,
    settings: Settings,
    iou_threshold: float = 0.3,
) -> list[BadCase]:
    """从一次 eval 运行里挑出需要片段分析的 badcase。

    - green_missed：benchmark 里 good（本应保留），但模型输出没命中它 -> 漏保留；
    - red_kept：benchmark 里 bad（本应删除），但模型输出命中了它 -> 误保留。
    这两类正是 benchmark 综合分的两个扣分来源，最值得让 Pro 逐一诊断。
    """
    url_by_case = {c.id: c.video_url for c in settings.cases}
    name_by_case = {c.id: c.name for c in settings.cases}
    bads: list[BadCase] = []

    for f in sorted(run_dir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        cid = data["case_id"]
        preds = (data.get("parsed") or {}).get("hook", []) or []
        items = benchmark["cases"].get(cid, {}).get("items", [])

        used: set[int] = set()
        for g in items:
            if g["quality"] not in ("good", "bad"):
                continue
            g_span = (float(g["start_time"]), float(g["end_time"]))
            best_j, best_iou = -1, 0.0
            for j, p in enumerate(preds):
                if j in used:
                    continue
                try:
                    p_span = (float(p["start_time"]), float(p["end_time"]))
                except (KeyError, TypeError, ValueError):
                    continue
                iou = _iou(p_span, g_span)
                if iou > best_iou:
                    best_iou, best_j = iou, j
            hit = best_j >= 0 and best_iou >= iou_threshold
            if hit:
                used.add(best_j)

            if g["quality"] == "good" and not hit:
                kind = "green_missed"
            elif g["quality"] == "bad" and hit:
                kind = "red_kept"
            else:
                continue

            bads.append(BadCase(
                case_id=cid,
                case_name=name_by_case.get(cid, cid),
                video_url=url_by_case.get(cid, ""),
                bench_id=g["id"],
                quality=g["quality"],
                kind=kind,
                start_ms=int(g["start_time"]),
                end_ms=int(g["end_time"]),
                content=g.get("content", ""),
                pred_hook=preds[best_j] if (kind == "red_kept" and best_j >= 0) else None,
            ))
    return bads


def analyze_badcases(
    settings: Settings,
    bads: list[BadCase],
    *,
    analysis_prompt: str,
    pro_model: str = "seed-2-1-pro",
    fps: float = 2.0,
    pad_ms: int = 3000,
    clips_dir: Path | None = None,
) -> list[SegmentVerdict]:
    client = ArkVideoClient(settings)
    clips_dir = clips_dir or (ROOT / "results" / "_clips")
    verdicts: list[SegmentVerdict] = []

    for bad in bads:
        clip = clips_dir / f"{bad.case_id}_{bad.bench_id}_{bad.kind}.mp4"
        print(f"[{bad.bench_id}] {bad.kind} 剪片段 {bad.start_ms}-{bad.end_ms}ms ...", flush=True)
        try:
            cut_clip(bad.video_url, bad.start_ms, bad.end_ms, clip, pad_ms=pad_ms)
        except Exception as e:  # noqa: BLE001
            verdicts.append(SegmentVerdict(bad, str(clip), None, "", f"ffmpeg 失败：{e}"))
            continue

        meta = _meta_text(bad, pad_ms)
        res = client.analyze_clip(
            clip_path=str(clip), prompt=analysis_prompt, meta_text=meta,
            model=pro_model, fps=fps,
        )
        verdicts.append(SegmentVerdict(bad, str(clip), res.parsed, res.raw_text, res.error))
        if res.error:
            print(f"  ✗ Pro 分析失败：{res.error}")
        else:
            v = (res.parsed or {}).get("verdict", "?")
            print(f"  ✓ 判定={v}")
    return verdicts
