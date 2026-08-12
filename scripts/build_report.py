"""生成《Seed 2.1 Turbo + 提示词 v1.4 测试报告》HTML。

新增：
1. 从 benchmark 与 v1.4 实测结果动态生成逐 case 可视化；
2. 每个 case 展示 benchmark vs v1.4 的时间轴对照；
3. 每个 case 展示预测输出列表、benchmark 命中状态、badcase 诊断摘要。
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
V14_DIR = ROOT / "results" / "v1.4_seed-2-1-turbo"
BENCHMARK_PATH = ROOT / "data" / "benchmark" / "benchmark.json"
SEGMENT_ANALYSIS_PATH = V14_DIR / "_segment_analysis.json"
V14_PROMPT = (ROOT / "prompts" / "v1.4.txt").read_text(encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


BENCHMARK = load_json(BENCHMARK_PATH)
SEGMENT_ANALYSIS = load_json(SEGMENT_ANALYSIS_PATH) if SEGMENT_ANALYSIS_PATH.exists() else []
IOU_THRESHOLD = float(BENCHMARK["_meta"].get("iou_threshold", 0.3))

# ---- 各版本 benchmark 汇总（均为 7 case 全量实测；v1 为 benchmark 来源）----
VERSIONS = [
    # name, score, green_kept, green_total, red_hit, red_total, note
    ("v1（原始版·benchmark来源）", 50.0, 2, 2, 15, 15, "松散召回，无验证链/无 badcase 排除；红色全部保留"),
    ("v1.3（v1.2×v3 融合）", 55.0, 1, 2, 6, 15, "恢复双输出+8步流程+E1-E4；召回偏宽，红色仍漏 6"),
    ("v2（聚焦hook+badcase门槛）", 61.7, 1, 2, 4, 15, "hook-only + 三力 + E1-E4"),
    ("v1.4（自动迭代终版）", 71.7, 1, 2, 1, 15, "hook-only + 三力 + E1-E7 + P1；红色仅漏 1"),
]

# v1 → v1.4 提示词关键改动
DIFFS = [
    ("输出范围", "同时产出 highlights + hook", "只产出 hook（highlights 恒为 []），算力集中，杜绝“泛看点召回”带来的误保留"),
    ("hook 定义", "“关键前置事件已成立、答案未展开”的较松描述", "收紧为：已发生事实 + 具体未解决问题 + 观众未知 + 答案未展开，并要求“非高度可预期”"),
    ("三力门槛", "无", "未解问题 + 情绪拉力 + 下一步期待，缺一即删（badcase 判定公式）"),
    ("验证链", "有三点自检，但无强制字段链", "established_fact → fact_evidence → open_question → 观众未知 → After End Check → 剧情驱动性"),
    ("专项排除", "无", "E1-E7 七条实证排除规则（高潮后部署/无征兆等待/真相已说全/察觉异常心理收尾/空洞宣告/评价感慨/仅变脸情绪）"),
    ("保护规则", "无", "P1：主角锁定追责对象+下令启动行动+真相未揭晓 → 必须保留，防误删优质 hook"),
    ("截点规则", "答案未泄露 > 画面稳定（较笼统）", "针对渐进式结果、指控揭穿类给出具体截点位置，压制“高潮已过/铺垫过渡”"),
    ("文案约束", "较宽松", "end_point_reason 固定“已成立：…；未展开：…”，description 不得描述未来"),
    ("排序", "明确未解问题优先", "叠加“即时冲击优先”：戛然而止感 > 心理活动/评价/流程完整"),
]

# 自动迭代产出的排除规则（来自 Pro 视频理解）
RULES = [
    ("E1", "v2 迭代", "高潮后失利方发怒/部署求援的过渡节点（停在布置任务/拨电话/下指令）"),
    ("E2", "v2 迭代", "“行动后等待结果”停在无征兆的空等初期（引鱼/下药/布陷阱…）"),
    ("E3", "v2→v1.3 强化", "真相/爆料已说全 + 对方第一波即时反应已现，后续只剩补充语句/情绪宣泄"),
    ("E4", "v2 迭代", "仅主角“察觉异常→戒备”的心理活动收尾，外部冲突尚未爆发"),
    ("E5", "v1.3 迭代", "无实质内容的空洞宣告/铺垫台词（“进门要守规矩”“你给我等着”）"),
    ("E6", "v1.3 迭代", "对已发生事件的评价/感慨类过渡对白；且严禁脑补片段外后续"),
    ("E7", "v1.3 迭代", "指控/揭穿后仅呈现另一方“本能变脸情绪反应”，尚无具体反驳/反制/升级"),
    ("P1", "保护规则", "主角锁定追责对象+情绪化放狠话+下令启动关键行动+真相未揭晓 → 保留"),
]

QUALITY_META = {
    "good": {"label": "绿色", "short": "绿", "color": "#37d67a", "cls": "good"},
    "bad": {"label": "红色", "short": "红", "color": "#ff5c7c", "cls": "bad"},
    "borderline": {"label": "黄色", "short": "黄", "color": "#ffb020", "cls": "yellow"},
    "acceptable": {"label": "白色", "short": "白", "color": "#d7dcef", "cls": "white"},
}

PRED_META = {
    "good": {"label": "命中绿色", "color": "#37d67a", "cls": "pred-good"},
    "bad": {"label": "误命中红色", "color": "#ff5c7c", "cls": "pred-bad"},
    "borderline": {"label": "命中黄色", "color": "#ffb020", "cls": "pred-yellow"},
    "acceptable": {"label": "命中白色", "color": "#d7dcef", "cls": "pred-white"},
    "extra": {"label": "额外输出", "color": "#4d8dff", "cls": "pred-extra"},
}


def esc(s) -> str:
    return html.escape(str(s))


def fmt_ms(ms: int | float | None) -> str:
    if ms is None:
        return "-"
    total_seconds = max(0, int(round(float(ms) / 1000)))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def shorten(text: str, limit: int = 48) -> str:
    text = str(text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    inter = max(0.0, end - start)
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def rel_to_report(path_like: str | Path) -> str:
    path = Path(path_like)
    abs_path = path if path.is_absolute() else (ROOT / path)
    return Path(os.path.relpath(abs_path, REPORT_DIR)).as_posix()


def build_case_data(case_id: str, case_bench: dict) -> dict:
    result = load_json(V14_DIR / f"{case_id}.json")
    pred_hooks = result.get("parsed", {}).get("hook", []) or []
    bench_items = case_bench["items"]
    analyses = [item for item in SEGMENT_ANALYSIS if item.get("case_id") == case_id]

    pred_rows = []
    for idx, pred in enumerate(pred_hooks, start=1):
        pred_rows.append({
            "idx": idx,
            "start_time": int(pred["start_time"]),
            "end_time": int(pred["end_time"]),
            "hook_type": pred.get("hook_type", ""),
            "open_question": pred.get("open_question", ""),
            "description": pred.get("description", ""),
            "status": "extra",
            "matched_bench_id": None,
            "match_quality": None,
            "match_iou": None,
            "status_label": PRED_META["extra"]["label"],
            "cls": PRED_META["extra"]["cls"],
        })

    used: set[int] = set()
    bench_rows = []
    green_total = green_kept = 0
    red_total = red_hit = 0
    yellow_kept = white_kept = 0

    for bench in bench_items:
        bench_span = (float(bench["start_time"]), float(bench["end_time"]))
        best_idx, best_iou = -1, 0.0
        for pred_idx, pred in enumerate(pred_hooks):
            if pred_idx in used:
                continue
            pred_span = (float(pred["start_time"]), float(pred["end_time"]))
            iou = _iou(pred_span, bench_span)
            if iou > best_iou:
                best_iou, best_idx = iou, pred_idx

        hit = best_idx >= 0 and best_iou >= IOU_THRESHOLD
        if hit:
            used.add(best_idx)
            pred_rows[best_idx]["status"] = bench["quality"]
            pred_rows[best_idx]["matched_bench_id"] = bench["id"]
            pred_rows[best_idx]["match_quality"] = bench["quality"]
            pred_rows[best_idx]["match_iou"] = round(best_iou, 3)
            pred_rows[best_idx]["status_label"] = PRED_META[bench["quality"]]["label"]
            pred_rows[best_idx]["cls"] = PRED_META[bench["quality"]]["cls"]

        quality = bench["quality"]
        if quality == "good":
            green_total += 1
            green_kept += int(hit)
            verdict = "✓保留" if hit else "✗漏保留"
        elif quality == "bad":
            red_total += 1
            red_hit += int(hit)
            verdict = "✗误命中" if hit else "✓已规避"
        elif quality == "borderline":
            yellow_kept += int(hit)
            verdict = "保留(可选)" if hit else "删除(可选)"
        else:
            white_kept += int(hit)
            verdict = "保留(中性)" if hit else "删除(中性)"

        bench_rows.append({
            "id": bench["id"],
            "start_time": int(bench["start_time"]),
            "end_time": int(bench["end_time"]),
            "hook_type": bench.get("hook_type", ""),
            "quality": quality,
            "quality_label": QUALITY_META[quality]["label"],
            "quality_short": QUALITY_META[quality]["short"],
            "quality_cls": QUALITY_META[quality]["cls"],
            "color": QUALITY_META[quality]["color"],
            "content": bench.get("content", ""),
            "expected": bench.get("expected", ""),
            "hit": hit,
            "verdict": verdict,
            "iou": round(best_iou, 3) if hit else None,
            "matched_pred_idx": best_idx + 1 if hit else None,
        })

    max_end = max(
        [item["end_time"] for item in bench_rows] + [item["end_time"] for item in pred_rows] + [1]
    )
    timeline_end = int(max_end * 1.05)

    return {
        "case_id": case_id,
        "name": case_bench["name"],
        "pred_rows": pred_rows,
        "bench_rows": bench_rows,
        "analyses": analyses,
        "n_pred": len(pred_rows),
        "green_total": green_total,
        "green_kept": green_kept,
        "red_total": red_total,
        "red_hit": red_hit,
        "yellow_kept": yellow_kept,
        "white_kept": white_kept,
        "timeline_end": timeline_end,
    }


def chip(label: str, cls: str = "") -> str:
    return f"<span class='chip {cls}'>{esc(label)}</span>"


def bar_svg(x: float, y: float, width: float, height: float, fill: str, stroke: str, label: str, title: str, text_fill: str = "#0b0f1f") -> str:
    text = ""
    if width >= 42:
        text = (
            f"<text x='{x + width / 2:.1f}' y='{y + height / 2 + 4:.1f}' text-anchor='middle' "
            f"fill='{text_fill}' font-size='11' font-weight='700'>{esc(label)}</text>"
        )
    return (
        f"<g><title>{esc(title)}</title>"
        f"<rect x='{x:.1f}' y='{y:.1f}' width='{width:.1f}' height='{height}' rx='6' ry='6' "
        f"fill='{fill}' stroke='{stroke}' stroke-width='1.2'></rect>{text}</g>"
    )


def build_case_timeline(case: dict) -> str:
    view_w = 1000
    left = 110
    top = 16
    track_w = 860
    row_h = 24
    row_gap = 28
    bench_y = top + 28
    pred_y = bench_y + row_h + row_gap
    axis_y = pred_y + row_h + 26
    total_h = axis_y + 30
    max_ms = max(case["timeline_end"], 1)

    parts = [
        f"<svg class='timeline' viewBox='0 0 {view_w} {total_h}' preserveAspectRatio='none'>",
        f"<rect x='{left}' y='{bench_y}' width='{track_w}' height='{row_h}' rx='8' fill='#121732' stroke='#2c3358'></rect>",
        f"<rect x='{left}' y='{pred_y}' width='{track_w}' height='{row_h}' rx='8' fill='#121732' stroke='#2c3358'></rect>",
        f"<text x='18' y='{bench_y + 16}' fill='#9aa3c0' font-size='12'>benchmark</text>",
        f"<text x='18' y='{pred_y + 16}' fill='#9aa3c0' font-size='12'>v1.4 输出</text>",
    ]

    for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = left + track_w * ratio
        parts.append(f"<line x1='{x:.1f}' y1='{bench_y - 10}' x2='{x:.1f}' y2='{axis_y - 8}' stroke='#2c3358' stroke-dasharray='4 4'></line>")
        parts.append(f"<text x='{x:.1f}' y='{axis_y + 14}' fill='#9aa3c0' font-size='11' text-anchor='middle'>{esc(fmt_ms(max_ms * ratio))}</text>")

    for idx, bench in enumerate(case["bench_rows"], start=1):
        x = left + track_w * (bench["start_time"] / max_ms)
        width = max(8, track_w * ((bench["end_time"] - bench["start_time"]) / max_ms))
        title = (
            f"{bench['id']} | {bench['quality_label']} | {fmt_ms(bench['start_time'])}-{fmt_ms(bench['end_time'])}\n"
            f"{bench['content']}\n结果：{bench['verdict']}"
        )
        parts.append(bar_svg(x, bench_y, width, row_h, bench["color"], "#0b0f1f", f"h{idx}", title))

    for pred in case["pred_rows"]:
        meta = PRED_META[pred["status"]]
        x = left + track_w * (pred["start_time"] / max_ms)
        width = max(8, track_w * ((pred["end_time"] - pred["start_time"]) / max_ms))
        match_note = pred["matched_bench_id"] or "未命中 benchmark"
        title = (
            f"P{pred['idx']} | {meta['label']} | {fmt_ms(pred['start_time'])}-{fmt_ms(pred['end_time'])}\n"
            f"type={pred['hook_type']} | 对齐={match_note}\n{pred['open_question'] or pred['description']}"
        )
        text_fill = "#0b0f1f" if pred["status"] in {"good", "bad", "borderline"} else "#13203f"
        parts.append(bar_svg(x, pred_y, width, row_h, meta["color"], "#0b0f1f", f"P{pred['idx']}", title, text_fill))

    parts.append("</svg>")
    return "".join(parts)


def build_prediction_rows(case: dict) -> str:
    rows = []
    for pred in case["pred_rows"]:
        rows.append(
            "<tr>"
            f"<td class='num'>P{pred['idx']}</td>"
            f"<td class='num'>{esc(fmt_ms(pred['start_time']))} - {esc(fmt_ms(pred['end_time']))}</td>"
            f"<td>{esc(pred['hook_type'])}</td>"
            f"<td><span class='mini-pill {esc(pred['cls'])}'>{esc(pred['status_label'])}</span></td>"
            f"<td>{esc(pred['matched_bench_id'] or '-')}</td>"
            f"<td>{esc(pred['match_iou'] if pred['match_iou'] is not None else '-')}</td>"
            f"<td>{esc(shorten(pred['open_question'] or pred['description'], 58))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='7' class='muted'>无输出</td></tr>"


def build_benchmark_rows(case: dict) -> str:
    rows = []
    for bench in case["bench_rows"]:
        rows.append(
            "<tr>"
            f"<td>{esc(bench['id'])}</td>"
            f"<td><span class='mini-pill bench-{esc(bench['quality_cls'])}'>{esc(bench['quality_label'])}</span></td>"
            f"<td class='num'>{esc(fmt_ms(bench['start_time']))} - {esc(fmt_ms(bench['end_time']))}</td>"
            f"<td>{esc(bench['verdict'])}</td>"
            f"<td>{esc(bench['matched_pred_idx'] and ('P' + str(bench['matched_pred_idx'])) or '-')}</td>"
            f"<td>{esc(shorten(bench['content'], 58))}</td>"
            "</tr>"
        )
    return "".join(rows)


def build_analysis_cards(case: dict) -> str:
    if not case["analyses"]:
        return ""
    cards = []
    for item in case["analyses"]:
        analysis = item.get("analysis", {}) or {}
        clip_rel = rel_to_report(item["clip"]) if item.get("clip") else None
        kind_label = "绿色漏保留" if item.get("kind") == "green_missed" else "红色误命中"
        verdict = analysis.get("verdict", "-")
        agree = "一致" if analysis.get("agree_with_human") else "不一致"
        link_html = f"<a href='{esc(clip_rel)}' target='_blank'>badcase 片段</a>" if clip_rel else ""
        clip_html = f"<p class='muted'>{link_html}</p>" if link_html else ""
        cards.append(
            "<div class='analysis-card'>"
            f"<div class='analysis-head'>{chip(kind_label, 'warn')} {chip(item.get('bench_id', '-'))} {chip('Pro判定: ' + verdict)} {chip('与人工: ' + agree)}</div>"
            f"<div class='analysis-body'><p><b>人工内容：</b>{esc(item.get('human_content', ''))}</p>"
            f"<p><b>证据：</b>{esc(analysis.get('evidence', '-'))}</p>"
            f"<p><b>提示词改进：</b>{esc(analysis.get('prompt_improvement', '-'))}</p>"
            f"{clip_html}</div>"
            "</div>"
        )
    return (
        "<div class='analysis-wrap'>"
        "<h3>该 case 的 badcase 诊断</h3>"
        + "".join(cards)
        + "</div>"
    )


def build_case_detail(case: dict, open_by_default: bool = False) -> str:
    summary = (
        chip(f"预测 {case['n_pred']}") +
        chip(f"绿 {case['green_kept']}/{case['green_total']}", "good") +
        chip(f"红 {case['red_hit']}/{case['red_total']}", "bad") +
        chip(f"黄 {case['yellow_kept']}", "warn") +
        chip(f"白 {case['white_kept']}")
    )
    return f"""
    <details class="case-detail" {'open' if open_by_default else ''}>
      <summary>
        <span class="case-title">{esc(case['case_id'])} · {esc(case['name'])}</span>
        <span class="case-summary-chips">{summary}</span>
      </summary>
      <div class="case-body">
        <div class="timeline-note">上轨是 benchmark，下轨是 v1.4 实际输出。鼠标悬停可看每个块的具体内容。</div>
        <div class="timeline-box">{build_case_timeline(case)}</div>
        <div class="legend">
          {chip('benchmark-绿', 'bench-good')}
          {chip('benchmark-红', 'bench-bad')}
          {chip('benchmark-黄', 'bench-yellow')}
          {chip('benchmark-白', 'bench-white')}
          {chip('输出命中绿', 'pred-good')}
          {chip('输出误命中红', 'pred-bad')}
          {chip('输出额外命中外', 'pred-extra')}
        </div>
        <div class="cols case-cols">
          <div>
            <h3>v1.4 输出列表</h3>
            <table class="compact">
              <thead><tr><th>序号</th><th>时间</th><th>类型</th><th>状态</th><th>对齐</th><th>IoU</th><th>open_question / 描述</th></tr></thead>
              <tbody>{build_prediction_rows(case)}</tbody>
            </table>
          </div>
          <div>
            <h3>benchmark 对照</h3>
            <table class="compact">
              <thead><tr><th>ID</th><th>颜色</th><th>时间</th><th>结果</th><th>命中输出</th><th>内容</th></tr></thead>
              <tbody>{build_benchmark_rows(case)}</tbody>
            </table>
          </div>
        </div>
        {build_analysis_cards(case)}
      </div>
    </details>
    """


def benchmark_score(green_total: int, green_kept: int, red_total: int, red_hit: int) -> dict:
    green_rate = green_kept / green_total if green_total else 1.0
    red_avoid = (red_total - red_hit) / red_total if red_total else 1.0
    score = 100 * (0.5 * green_rate + 0.5 * red_avoid)
    return {
        "green_rate": round(green_rate, 4),
        "red_avoid_rate": round(red_avoid, 4),
        "score": round(score, 1),
    }


CASE_DATA = [
    build_case_data(case_id, case_bench)
    for case_id, case_bench in BENCHMARK["cases"].items()
]

TOTAL_GREEN = sum(case["green_total"] for case in CASE_DATA)
TOTAL_GREEN_KEPT = sum(case["green_kept"] for case in CASE_DATA)
TOTAL_RED = sum(case["red_total"] for case in CASE_DATA)
TOTAL_RED_HIT = sum(case["red_hit"] for case in CASE_DATA)
TOTAL_PRED = sum(case["n_pred"] for case in CASE_DATA)
TOTAL_BENCH_ITEMS = sum(len(case["bench_rows"]) for case in CASE_DATA)
SUMMARY = benchmark_score(TOTAL_GREEN, TOTAL_GREEN_KEPT, TOTAL_RED, TOTAL_RED_HIT)

bars = ""
for name, score, gk, gt, rh, rt, note in VERSIONS:
    pct = score
    hot = "v14" if name.startswith("v1.4") else ("base" if name.startswith("v1（") else "mid")
    bars += f"""
    <div class="bar-row">
      <div class="bar-label">{esc(name)}</div>
      <div class="bar-track"><div class="bar-fill {hot}" style="width:{pct}%"></div>
        <span class="bar-val">{score}</span></div>
      <div class="bar-sub">绿保留 {gk}/{gt}　红误命中 {rh}/{rt}　<span class="muted">{esc(note)}</span></div>
    </div>"""

ver_rows = "".join(
    f"<tr class='{ 'hl' if n.startswith('v1.4') else ''}'><td>{esc(n)}</td><td class='num'>{s}</td>"
    f"<td class='num'>{gk}/{gt}</td><td class='num'>{rh}/{rt}</td>"
    f"<td class='num'>{round((rt-rh)/rt*100)}%</td></tr>"
    for n, s, gk, gt, rh, rt, note in VERSIONS
)

case_rows = "".join(
    f"<tr><td>{esc(case['case_id'])}</td><td>{esc(case['name'])}</td><td class='num'>{case['n_pred']}</td>"
    f"<td class='num'>{case['green_kept']}/{case['green_total']}</td>"
    f"<td class='num red'>{case['red_hit']}/{case['red_total']}</td>"
    f"<td class='num'>{case['yellow_kept']}</td><td class='num'>{case['white_kept']}</td></tr>"
    for case in CASE_DATA
)

diff_rows = "".join(
    f"<tr><td class='dim'>{esc(dim)}</td><td class='v1cell'>{esc(a)}</td><td class='v14cell'>{esc(b)}</td></tr>"
    for dim, a, b in DIFFS
)

rule_rows = "".join(
    f"<tr><td class='tag'>{esc(code)}</td><td class='muted'>{esc(src)}</td><td>{esc(desc)}</td></tr>"
    for code, src, desc in RULES
)

case_visuals = "".join(
    build_case_detail(case, open_by_default=index < 2)
    for index, case in enumerate(CASE_DATA)
)

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seed 2.1 Turbo + 提示词 v1.4 测试报告</title>
<style>
  :root {{
    --bg:#0f1220; --card:#1a1f35; --card2:#222844; --ink:#e8ebf5; --muted:#9aa3c0;
    --line:#2c3358; --green:#37d67a; --red:#ff5c7c; --blue:#4d8dff; --gold:#ffb020;
    --white:#d7dcef; --v14:#37d67a;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:linear-gradient(160deg,#0d1020,#141833 60%,#0f1328);
    color:var(--ink); font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
    line-height:1.65; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:48px 24px 80px; }}
  header.hero {{ text-align:center; padding:40px 20px 28px; }}
  .hero h1 {{ font-size:30px; margin:0 0 10px; letter-spacing:.5px; }}
  .hero .sub {{ color:var(--muted); font-size:15px; }}
  .pill, .chip {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px;
    background:#20264a; color:var(--muted); margin:2px 4px; border:1px solid var(--line); }}
  .chip.good, .mini-pill.pred-good, .mini-pill.bench-good, .chip.bench-good {{ color:#0f1a12; background:var(--green); border-color:transparent; }}
  .chip.bad, .mini-pill.pred-bad, .mini-pill.bench-bad, .chip.bench-bad {{ color:#240814; background:var(--red); border-color:transparent; }}
  .chip.warn, .mini-pill.pred-yellow, .mini-pill.bench-yellow, .chip.bench-yellow {{ color:#241702; background:var(--gold); border-color:transparent; }}
  .mini-pill.pred-white, .mini-pill.bench-white, .chip.bench-white {{ color:#1a223e; background:var(--white); border-color:transparent; }}
  .mini-pill.pred-extra, .chip.pred-extra {{ color:#0d1733; background:var(--blue); border-color:transparent; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:28px 0 8px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px 18px; text-align:center; }}
  .kpi .big {{ font-size:34px; font-weight:800; }}
  .kpi .lab {{ color:var(--muted); font-size:13px; margin-top:6px; }}
  .kpi.win .big {{ color:var(--v14); }}
  .kpi .delta {{ font-size:12px; margin-top:4px; }}
  .up {{ color:var(--green); }} .down {{ color:var(--red); }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:26px 28px; margin:22px 0; }}
  section h2 {{ font-size:20px; margin:0 0 16px; display:flex; align-items:center; gap:10px; }}
  section h2 .n {{ background:var(--blue); color:#fff; width:26px; height:26px; border-radius:8px;
    display:inline-flex; align-items:center; justify-content:center; font-size:14px; }}
  section h3 {{ font-size:15px; margin:0 0 10px; }}
  p.lead {{ color:var(--muted); margin-top:-4px; }}
  .bar-row {{ margin:14px 0; }}
  .bar-label {{ font-size:14px; margin-bottom:6px; }}
  .bar-track {{ position:relative; background:#141838; border:1px solid var(--line);
    border-radius:10px; height:30px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:9px 0 0 9px; background:var(--blue); transition:width .6s; }}
  .bar-fill.base {{ background:#5b6488; }}
  .bar-fill.mid {{ background:var(--gold); }}
  .bar-fill.v14 {{ background:linear-gradient(90deg,#37d67a,#28b6ff); }}
  .bar-val {{ position:absolute; right:10px; top:4px; font-weight:700; font-size:14px; }}
  .bar-sub {{ font-size:12px; color:var(--ink); margin-top:5px; }}
  .muted {{ color:var(--muted); }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:13px; }}
  td.num {{ text-align:center; font-variant-numeric:tabular-nums; }}
  td.red {{ color:var(--red); }}
  tr.hl {{ background:rgba(55,214,122,.10); }}
  tr.hl td {{ font-weight:700; }}
  .dim {{ color:var(--gold); font-weight:600; white-space:nowrap; }}
  .v1cell {{ color:var(--muted); }}
  .v14cell {{ color:var(--ink); }}
  .tag {{ font-weight:800; color:var(--blue); }}
  pre {{ background:#0c0f22; border:1px solid var(--line); border-radius:12px; padding:18px;
    overflow:auto; font-size:12.5px; line-height:1.6; color:#cdd4ee; max-height:640px;
    white-space:pre-wrap; word-break:break-word; }}
  .flow {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:6px 0 2px; }}
  .step {{ background:var(--card2); border:1px solid var(--line); border-radius:8px; padding:6px 12px; font-size:13px; }}
  .arrow {{ color:var(--muted); }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  .note {{ background:#171b38; border-left:3px solid var(--gold); padding:12px 16px; border-radius:8px; font-size:13.5px; color:var(--muted); }}
  .legend {{ margin-top:10px; }}
  .timeline-note {{ color:var(--muted); font-size:13px; margin-bottom:10px; }}
  .timeline-box {{ background:#11152a; border:1px solid var(--line); border-radius:14px; padding:14px; overflow:hidden; }}
  .timeline {{ width:100%; height:188px; display:block; }}
  .case-detail {{ border:1px solid var(--line); background:#161b31; border-radius:16px; margin:16px 0; overflow:hidden; }}
  .case-detail summary {{ list-style:none; cursor:pointer; padding:18px 20px; display:flex; gap:12px; align-items:flex-start; justify-content:space-between; }}
  .case-detail summary::-webkit-details-marker {{ display:none; }}
  .case-detail[open] summary {{ border-bottom:1px solid var(--line); background:#1b213d; }}
  .case-title {{ font-size:16px; font-weight:700; }}
  .case-summary-chips {{ text-align:right; }}
  .case-body {{ padding:18px 20px 22px; }}
  .case-cols {{ margin-top:14px; }}
  .compact th, .compact td {{ padding:8px 10px; font-size:12.5px; }}
  .mini-pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; border:1px solid var(--line); }}
  .analysis-wrap {{ margin-top:16px; }}
  .analysis-card {{ background:#121732; border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin-top:10px; }}
  .analysis-head {{ margin-bottom:8px; }}
  .analysis-body p {{ margin:8px 0; font-size:13px; }}
  a {{ color:#7db0ff; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:34px; }}
  @media (max-width:900px) {{
    .kpis{{grid-template-columns:repeat(2,1fr);}}
    .cols{{grid-template-columns:1fr;}}
    .case-detail summary{{flex-direction:column;}}
    .case-summary-chips{{text-align:left;}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>Seed 2.1 Turbo · 提示词 v1.4 测试报告</h1>
    <div class="sub">短剧 Hook 时间戳提取 · 自动化提示词迭代（v1 → v1.3 → v1.4）</div>
    <div style="margin-top:12px">
      <span class="pill">主模型 Seed 2.1 Turbo（提取）</span>
      <span class="pill">Seed 2.1 Pro（片段视频理解·诊断）</span>
      <span class="pill">7 个短剧 · benchmark {TOTAL_BENCH_ITEMS} 条 hook</span>
      <span class="pill">评测口径：绿色保留率 + 红色规避率</span>
    </div>
  </header>

  <div class="kpis">
    <div class="kpi win"><div class="big">{SUMMARY['score']}</div><div class="lab">v1.4 综合分 / 100</div><div class="delta up">▲ 相比 v1 +{round(SUMMARY['score'] - 50.0, 1)}</div></div>
    <div class="kpi win"><div class="big">{round(SUMMARY['red_avoid_rate'] * 100)}%</div><div class="lab">红色 badcase 规避率</div><div class="delta up">▲ v1 为 0%</div></div>
    <div class="kpi"><div class="big">{TOTAL_RED_HIT}<span class="muted" style="font-size:18px">/{TOTAL_RED}</span></div><div class="lab">红色误命中（越低越好）</div><div class="delta up">▼ v1 为 15/15</div></div>
    <div class="kpi"><div class="big">{TOTAL_PRED}</div><div class="lab">v1.4 输出 hook 总数</div><div class="delta muted">v1 为 54，更精不滥</div></div>
  </div>

  <section>
    <h2><span class="n">1</span>综合分对比（4 版本 · 全 7 case 实测）</h2>
    <p class="lead">评测只看两件事：该保留的绿色有没有保住、该删除的红色有没有删掉。综合分 = 50% × 绿色保留率 + 50% × 红色规避率。</p>
    {bars}
    <table style="margin-top:18px">
      <thead><tr><th>版本</th><th class="num">综合分</th><th class="num">🟢绿保留</th><th class="num">🔴红误命中</th><th class="num">红规避率</th></tr></thead>
      <tbody>{ver_rows}</tbody>
    </table>
    <p class="note" style="margin-top:16px">说明：v1 本身是 benchmark 的来源，因此它“保住了全部绿色”，但也“保留了全部红色”（红规避率 0%）。真正的优化目标，是在尽量保住绿色的前提下把红色规避率拉高。v1.4 把红色误命中从 15 压到 1。</p>
  </section>

  <section>
    <h2><span class="n">2</span>优化效果：v1.4 逐 case 汇总</h2>
    <p class="lead">先看 case 级指标，再往下看每个 case 的时间轴可视化和具体输出内容。</p>
    <table>
      <thead><tr><th>Case</th><th>剧名</th><th class="num">预测数</th><th class="num">🟢保留</th><th class="num">🔴误命中</th><th class="num">🟡保留</th><th class="num">⬜保留</th></tr></thead>
      <tbody>{case_rows}</tbody>
    </table>
    <div class="note" style="margin-top:16px">下面每个 case 都加了可视化时间轴：上轨是 benchmark， 下轨是 v1.4 实际输出。可以直接看出哪些点被保住、哪些红点被误命中、以及哪些输出是 benchmark 外的额外召回。</div>
  </section>

  <section>
    <h2><span class="n">3</span>每个 Case 的可视化输出结果</h2>
    <p class="lead">默认展开前两个 case。其余 case 点开即可看完整时间轴、输出列表、benchmark 对照和 badcase 诊断。</p>
    {case_visuals}
  </section>

  <section>
    <h2><span class="n">4</span>自动化迭代是怎么产出 v1.4 的</h2>
    <div class="flow">
      <span class="step">① Turbo + 当前 prompt 提取 hook</span><span class="arrow">→</span>
      <span class="step">② 与 benchmark 对比，挑出 badcase</span><span class="arrow">→</span>
      <span class="step">③ ffmpeg 剪出 badcase 片段</span><span class="arrow">→</span>
      <span class="step">④ Seed 2.1 Pro 视频理解逐条诊断</span><span class="arrow">→</span>
      <span class="step">⑤ 反推排除/保护规则，写入新 prompt</span>
    </div>
    <p class="lead" style="margin-top:14px">v1.3（55.0 分）的 badcase 片段送 Pro 逐一看片判断，Pro 判定与人工研判 <b>100% 一致</b>，提炼出以下规则（E5-E7 为本轮新增）：</p>
    <table>
      <thead><tr><th>规则</th><th>来源</th><th>命中即删除 / 保留的情形</th></tr></thead>
      <tbody>{rule_rows}</tbody>
    </table>
  </section>

  <section>
    <h2><span class="n">5</span>提示词改动：v1 → v1.4</h2>
    <p class="lead">v1 是“松散召回 + 双输出 + 无验证/无排除”；v1.4 是“hook-only + 三力门槛 + 验证链 + E1-E7 排除 + P1 保护”。</p>
    <table>
      <thead><tr><th>维度</th><th>v1（原始）</th><th>v1.4（终版）</th></tr></thead>
      <tbody>{diff_rows}</tbody>
    </table>
    <p style="margin-top:16px">v1.4 的 hook 流程（沿用并强化 v1.2 的骨架）：</p>
    <div class="flow">
      <span class="step">定义/三力门槛</span><span class="arrow">→</span>
      <span class="step">候选生成</span><span class="arrow">→</span>
      <span class="step">验证链</span><span class="arrow">→</span>
      <span class="step">hook_type</span><span class="arrow">→</span>
      <span class="step">排除规则 E1-E7</span><span class="arrow">→</span>
      <span class="step">截点</span><span class="arrow">→</span>
      <span class="step">去重</span><span class="arrow">→</span>
      <span class="step">排序（即时冲击优先）</span>
    </div>
  </section>

  <section>
    <h2><span class="n">6</span>最终版提示词 v1.4（完整稿）</h2>
    <p class="lead">以下为 <code>prompts/v1.4.txt</code> 全文，可直接作为 Seed 2.1 Turbo 的 system prompt 使用。</p>
    <pre>{esc(V14_PROMPT)}</pre>
  </section>

  <footer>
    创量魔剪 · 短剧 Hook 提取自动化迭代 ｜ 数据由 Seed 2.1 Turbo 提取、Seed 2.1 Pro 诊断、benchmark 客观评测生成
  </footer>
</div>
</body>
</html>
"""

out = REPORT_DIR / "Seed_2.1_Turbo_v1.4_测试报告.html"
out.write_text(HTML, encoding="utf-8")
print("written:", out, "bytes:", len(HTML))
