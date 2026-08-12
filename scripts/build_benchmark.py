"""从人工标注派生标准答案 benchmark。

单一数据源：data/annotations/annotations.json（含 v1+Turbo 结果与人工 quality）。
本脚本把它规范化为 data/benchmark/benchmark.json，给每条 hook 分配稳定 id 与
「期望动作」，并写入评分规则。annotations 更新后重跑本脚本即可保持一致：

    python scripts/build_benchmark.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data" / "annotations" / "annotations.json"
OUT = ROOT / "data" / "benchmark" / "benchmark.json"

# 人工研判颜色 -> 期望动作。scored=True 的等级参与打分，其余中性仅展示。
QUALITY_RULE = {
    "good":       {"color": "绿", "expected": "keep",          "scored": True,
                   "desc": "必须保留；允许少量时间偏差（IoU 达阈值即视为成功保留）"},
    "bad":        {"color": "红", "expected": "drop",          "scored": True,
                   "desc": "必须删除；预测命中即判失败"},
    "borderline": {"color": "黄", "expected": "optional_keep", "scored": False,
                   "desc": "可删可留；若保留，end_time 相比基准有更优微调更好（需人工确认）"},
    "acceptable": {"color": "白", "expected": "optional",      "scored": False,
                   "desc": "可删可留，中性不计分"},
}


def main() -> None:
    ann = json.loads(ANN.read_text(encoding="utf-8"))
    cases: dict[str, dict] = {}
    for cid, c in ann.items():
        if cid.startswith("_"):
            continue
        items = []
        for i, h in enumerate(c["hooks"], 1):
            q = h["quality"]
            items.append({
                "id": f"{cid}-h{i}",
                "start_time": h["start_time"],
                "end_time": h["end_time"],
                "hook_type": h.get("hook_type"),
                "quality": q,
                "expected": QUALITY_RULE[q]["expected"],
                "content": h.get("content", ""),
            })
        cases[cid] = {"name": c["name"], "items": items}

    bench = {
        "_meta": {
            "purpose": "提示词迭代效果评估的标准答案。后续版本输出与本 benchmark 比对。",
            "derived_from": "data/annotations/annotations.json",
            "rebuild": "python scripts/build_benchmark.py",
            "time_unit": "ms",
            "iou_threshold": 0.3,
            "grading_rules": QUALITY_RULE,
            "score_formula": "benchmark_score = 100 * (0.5 * 绿色保留率 + 0.5 * 红色规避率)",
            "score_note": "绿(good)、红(bad)为硬约束参与打分；黄(borderline)、白(acceptable)可选，仅展示不计分。",
        },
        "cases": cases,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bench, ensure_ascii=False, indent=2), encoding="utf-8")

    # 打印分布，便于核对
    from collections import Counter
    dist = Counter(it["quality"] for c in cases.values() for it in c["items"])
    total = sum(dist.values())
    print(f"benchmark 已生成：{OUT}")
    print(f"共 {len(cases)} 个 case，{total} 条 hook，分布：{dict(dist)}")


if __name__ == "__main__":
    main()
