"""评估器：将模型输出的 hook 与人工标注对齐，量化时间戳准确性。

核心指标（hook 提取的痛点是时间戳不准，所以重点评时间）：
- match：预测 hook 与某条标注按时间重叠（IoU）匹配上算命中；
- iou：命中对的区间交并比，衡量整体贴合度；
- end_time_err_ms：命中对的 end_time 绝对误差（hook 的价值全在结尾停顿点，
  end_time 误差是最关键指标）；
- type_acc：命中对里 hook_type 是否一致。
标注中 quality=bad 的条目视为"不应被这样切"的负样本，预测若与之高 IoU 命中，
计入 hit_bad，用于观察新 prompt 是否避开了旧 badcase。
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    inter = max(0.0, e - s)
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class CaseEval:
    case_id: str
    name: str
    n_pred: int
    n_gold: int
    n_matched: int
    hit_bad: int
    mean_iou: float
    mean_end_err_ms: float
    type_acc: float
    details: list[dict] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.n_matched / self.n_gold if self.n_gold else 0.0

    @property
    def precision(self) -> float:
        return self.n_matched / self.n_pred if self.n_pred else 0.0


def evaluate_case(
    case_id: str,
    name: str,
    pred_hooks: list[dict],
    gold_hooks: list[dict],
    iou_threshold: float = 0.3,
) -> CaseEval:
    """贪心匹配：每个 gold 找 IoU 最高且过阈值的未占用 pred。"""
    used: set[int] = set()
    matched = 0
    ious: list[float] = []
    end_errs: list[float] = []
    type_hits = 0
    hit_bad = 0
    details: list[dict] = []

    for g in gold_hooks:
        g_span = (float(g["start_time"]), float(g["end_time"]))
        best_j, best_iou = -1, 0.0
        for j, p in enumerate(pred_hooks):
            if j in used:
                continue
            try:
                p_span = (float(p["start_time"]), float(p["end_time"]))
            except (KeyError, TypeError, ValueError):
                continue
            iou = _iou(p_span, g_span)
            if iou > best_iou:
                best_iou, best_j = iou, j

        if best_j >= 0 and best_iou >= iou_threshold:
            used.add(best_j)
            matched += 1
            p = pred_hooks[best_j]
            end_err = abs(float(p["end_time"]) - g_span[1])
            ious.append(best_iou)
            end_errs.append(end_err)
            same_type = str(p.get("hook_type")) == str(g.get("hook_type"))
            type_hits += int(same_type)
            if g.get("quality") == "bad":
                hit_bad += 1
            details.append({
                "gold": g.get("content", "")[:30],
                "quality": g.get("quality"),
                "iou": round(best_iou, 3),
                "end_err_ms": int(end_err),
                "gold_type": g.get("hook_type"),
                "pred_type": p.get("hook_type"),
                "type_ok": same_type,
            })

    return CaseEval(
        case_id=case_id,
        name=name,
        n_pred=len(pred_hooks),
        n_gold=len(gold_hooks),
        n_matched=matched,
        hit_bad=hit_bad,
        mean_iou=round(sum(ious) / len(ious), 3) if ious else 0.0,
        mean_end_err_ms=round(sum(end_errs) / len(end_errs), 1) if end_errs else 0.0,
        type_acc=round(type_hits / matched, 3) if matched else 0.0,
        details=details,
    )


@dataclass
class BenchCaseEval:
    """针对 benchmark 的 case 级评分（面向"保留绿/删红"目标）。"""
    case_id: str
    name: str
    n_pred: int
    green_total: int
    green_kept: int          # 绿色被成功保留（预测按 IoU 命中）
    red_total: int
    red_hit: int             # 红色被错误命中（越少越好）
    yellow_kept: int         # 黄色被保留数（中性，仅展示）
    white_kept: int          # 白色被保留数（中性，仅展示）
    details: list[dict] = field(default_factory=list)


def evaluate_benchmark_case(
    case_id: str,
    name: str,
    pred_hooks: list[dict],
    bench_items: list[dict],
    iou_threshold: float = 0.3,
) -> BenchCaseEval:
    """按 benchmark 的期望动作打分。

    - green(good)：期望 keep，预测命中 => green_kept +1（成功）；未命中 => 漏保留。
    - red(bad)：期望 drop，预测命中 => red_hit +1（失败）。
    - yellow/white：中性，仅统计是否被保留用于展示。
    每个 benchmark 条目最多匹配一个未占用的预测（贪心取最高 IoU）。
    """
    used: set[int] = set()
    green_total = green_kept = 0
    red_total = red_hit = 0
    yellow_kept = white_kept = 0
    details: list[dict] = []

    for g in bench_items:
        g_span = (float(g["start_time"]), float(g["end_time"]))
        best_j, best_iou = -1, 0.0
        for j, p in enumerate(pred_hooks):
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

        q = g["quality"]
        end_err = None
        if hit:
            end_err = int(abs(float(pred_hooks[best_j]["end_time"]) - g_span[1]))

        if q == "good":
            green_total += 1
            green_kept += int(hit)
            verdict = "✓保留" if hit else "✗漏保留"
        elif q == "bad":
            red_total += 1
            red_hit += int(hit)
            verdict = "✗误命中" if hit else "✓已规避"
        elif q == "borderline":
            yellow_kept += int(hit)
            verdict = "保留(可选)" if hit else "删除(可选)"
        else:  # acceptable
            white_kept += int(hit)
            verdict = "保留(中性)" if hit else "删除(中性)"

        details.append({
            "id": g["id"],
            "quality": q,
            "expected": g["expected"],
            "hit": hit,
            "iou": round(best_iou, 3) if hit else 0.0,
            "end_err_ms": end_err,
            "verdict": verdict,
            "content": g.get("content", "")[:28],
        })

    return BenchCaseEval(
        case_id=case_id, name=name, n_pred=len(pred_hooks),
        green_total=green_total, green_kept=green_kept,
        red_total=red_total, red_hit=red_hit,
        yellow_kept=yellow_kept, white_kept=white_kept,
        details=details,
    )


def benchmark_score(green_total: int, green_kept: int,
                    red_total: int, red_hit: int) -> dict:
    """综合分：0.5*绿色保留率 + 0.5*红色规避率，满分 100。"""
    green_rate = green_kept / green_total if green_total else 1.0
    red_avoid = (red_total - red_hit) / red_total if red_total else 1.0
    score = 100 * (0.5 * green_rate + 0.5 * red_avoid)
    return {
        "green_rate": round(green_rate, 4),
        "red_avoid_rate": round(red_avoid, 4),
        "score": round(score, 1),
    }
