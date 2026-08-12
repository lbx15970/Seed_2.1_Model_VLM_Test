"""命令行入口。

用法：
  # 跑单个 case
  python -m hook_extractor.cli extract --case case1 --prompt v2 --model seed-2-1-turbo

  # 跑全部 case（可指定 fps 覆盖默认）
  python -m hook_extractor.cli extract --all --prompt v2 --fps 2.0

  # 对某次运行结果做评估（与人工标注对比）
  python -m hook_extractor.cli eval --run results/v2_seed-2-1-turbo

结果目录结构：
  results/<prompt>_<model>/<case_id>.json   # 每个 case 的原始+解析输出
  results/<prompt>_<model>/_eval.md          # eval 生成的对比报告
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import ROOT, load_settings
from .evaluator import (
    BenchCaseEval,
    CaseEval,
    benchmark_score,
    evaluate_benchmark_case,
    evaluate_case,
)


def _run_dir(prompt: str, model: str) -> Path:
    d = ROOT / "results" / f"{prompt}_{model}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_prompt(prompt: str) -> str:
    p = ROOT / "prompts" / f"{prompt}.txt"
    if not p.exists():
        sys.exit(f"提示词文件不存在：{p}")
    return p.read_text(encoding="utf-8")


def cmd_extract(args: argparse.Namespace) -> None:
    from .ark_client import ArkVideoClient  # 懒加载：eval 命令无需视频 SDK

    settings = load_settings()
    client = ArkVideoClient(settings)
    prompt_text = _load_prompt(args.prompt)
    fps = args.fps if args.fps is not None else settings.default_fps
    model = args.model or settings.default_model

    if args.all:
        targets = settings.cases
    else:
        if not args.case:
            sys.exit("请用 --case 指定 case_id，或用 --all 跑全部")
        targets = [settings.get_case(args.case)]

    out_dir = _run_dir(args.prompt, model)
    print(f"端点={settings.endpoint} base_url={settings.base_url}")
    print(f"prompt={args.prompt} model={model} fps={fps} -> {out_dir}\n")

    for case in targets:
        print(f"[{case.id}] {case.name} 提取中 ...", flush=True)
        t0 = time.time()
        res = client.extract(
            video_url=case.video_url, prompt=prompt_text, model=model, fps=fps
        )
        elapsed = round(time.time() - t0, 1)
        payload = {
            "case_id": case.id,
            "name": case.name,
            "video_url": case.video_url,
            "prompt": args.prompt,
            "model": res.model_id,
            "fps": fps,
            "elapsed_s": elapsed,
            "usage": res.usage,
            "error": res.error,
            "raw_text": res.raw_text,
            "parsed": res.parsed,
        }
        (out_dir / f"{case.id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if res.error:
            print(f"  ✗ 失败（{elapsed}s）：{res.error}\n")
        else:
            n = len((res.parsed or {}).get("hook", []))
            print(f"  ✓ 完成（{elapsed}s），hook 数={n}\n")


def cmd_eval(args: argparse.Namespace) -> None:
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    if not run_dir.exists():
        sys.exit(f"运行目录不存在：{run_dir}")

    ann_path = ROOT / "data" / "annotations" / "annotations.json"
    annotations = json.loads(ann_path.read_text(encoding="utf-8"))

    bench_path = ROOT / "data" / "benchmark" / "benchmark.json"
    bench = json.loads(bench_path.read_text(encoding="utf-8")) if bench_path.exists() else None

    evals: list[CaseEval] = []
    bench_evals: list[BenchCaseEval] = []
    for f in sorted(run_dir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        cid = data["case_id"]
        gold = annotations.get(cid, {}).get("hooks", [])
        pred = (data.get("parsed") or {}).get("hook", []) or []
        evals.append(
            evaluate_case(cid, data.get("name", cid), pred, gold, args.iou)
        )
        if bench:
            items = bench["cases"].get(cid, {}).get("items", [])
            bench_evals.append(
                evaluate_benchmark_case(cid, data.get("name", cid), pred, items, args.iou)
            )

    report = _render_report(run_dir.name, evals, bench_evals, args.iou)
    out = run_dir / "_eval.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n报告已写入：{out}")


def _render_benchmark(bench_evals: list[BenchCaseEval]) -> list[str]:
    """Benchmark 达成度板块（面向"保留绿/删红"目标）。"""
    if not bench_evals:
        return []
    g_tot = sum(b.green_total for b in bench_evals)
    g_kept = sum(b.green_kept for b in bench_evals)
    r_tot = sum(b.red_total for b in bench_evals)
    r_hit = sum(b.red_hit for b in bench_evals)
    agg = benchmark_score(g_tot, g_kept, r_tot, r_hit)

    lines = [
        "## Benchmark 达成度（核心）",
        "",
        f"**综合分：{agg['score']} / 100**"
        f"（= 50% × 绿色保留率 {agg['green_rate']:.0%} + 50% × 红色规避率 {agg['red_avoid_rate']:.0%}）",
        "",
        f"- 🟢 绿色(good)保留：{g_kept}/{g_tot}（越高越好，必须保留的优质 hook）",
        f"- 🔴 红色(bad)误命中：{r_hit}/{r_tot}（越低越好，必须删除的 badcase）",
        "- 🟡 黄色(borderline)/⬜ 白色(acceptable)：可选，不计分，仅展示",
        "",
        "| Case | 剧名 | 预测数 | 🟢保留 | 🔴误命中 | 🟡保留 | ⬜保留 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for b in bench_evals:
        lines.append(
            f"| {b.case_id} | {b.name} | {b.n_pred} "
            f"| {b.green_kept}/{b.green_total} | {b.red_hit}/{b.red_total} "
            f"| {b.yellow_kept} | {b.white_kept} |"
        )
    lines.append("")
    return lines


def _render_report(
    run_name: str,
    evals: list[CaseEval],
    bench_evals: list[BenchCaseEval],
    iou_th: float,
) -> str:
    lines = [
        f"# 评估报告 · {run_name}",
        "",
        f"IoU 匹配阈值：{iou_th}｜时间单位：ms",
        "",
    ]
    lines += _render_benchmark(bench_evals)
    lines += [
        "## 时间戳对齐指标（辅助）",
        "",
        "| Case | 剧名 | 预测 | 标注 | 命中 | 召回 | 精确 | 均IoU | 均end误差 | 类型准确 | 命中旧bad |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    tot_pred = tot_gold = tot_match = tot_bad = 0
    w_iou = w_end = w_type = 0.0
    for e in evals:
        lines.append(
            f"| {e.case_id} | {e.name} | {e.n_pred} | {e.n_gold} | {e.n_matched} "
            f"| {e.recall:.2f} | {e.precision:.2f} | {e.mean_iou} | {e.mean_end_err_ms} "
            f"| {e.type_acc} | {e.hit_bad} |"
        )
        tot_pred += e.n_pred
        tot_gold += e.n_gold
        tot_match += e.n_matched
        tot_bad += e.hit_bad
        w_iou += e.mean_iou * e.n_matched
        w_end += e.mean_end_err_ms * e.n_matched
        w_type += e.type_acc * e.n_matched

    m = tot_match or 1
    lines += [
        "",
        "## 汇总",
        "",
        f"- 总召回：{tot_match}/{tot_gold} = {tot_match / (tot_gold or 1):.2%}",
        f"- 总精确：{tot_match}/{tot_pred} = {tot_match / (tot_pred or 1):.2%}",
        f"- 加权均 IoU：{w_iou / m:.3f}",
        f"- 加权均 end_time 误差：{w_end / m:.0f} ms",
        f"- 加权类型准确率：{w_type / m:.2%}",
        f"- 命中旧 badcase 数：{tot_bad}（越低越好，说明规避了 v1 的坏截点）",
        "",
        "## 逐条明细",
        "",
    ]
    for e in evals:
        lines.append(f"### {e.case_id} {e.name}")
        if not e.details:
            lines.append("- 无命中（预测与标注 IoU 全部低于阈值）\n")
            continue
        lines.append("| 标注内容 | 质量 | IoU | end误差(ms) | 标注类型→预测类型 | 类型对 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for d in e.details:
            lines.append(
                f"| {d['gold']} | {d['quality']} | {d['iou']} | {d['end_err_ms']} "
                f"| {d['gold_type']}→{d['pred_type']} | {'✓' if d['type_ok'] else '✗'} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(prog="hook_extractor", description="短剧 Hook 时间戳提取与评估")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="调用模型提取 hook")
    pe.add_argument("--case", help="case_id，如 case1")
    pe.add_argument("--all", action="store_true", help="跑全部 case")
    pe.add_argument("--prompt", default="v2", help="提示词版本名（prompts/<name>.txt）")
    pe.add_argument("--model", help="模型别名或 Model ID，默认取 .env DEFAULT_MODEL")
    pe.add_argument("--fps", type=float, help="抽帧率，默认取 .env DEFAULT_FPS")
    pe.set_defaults(func=cmd_extract)

    pv = sub.add_parser("eval", help="对比人工标注评估某次运行")
    pv.add_argument("--run", required=True, help="结果目录，如 results/v2_seed-2-1-turbo")
    pv.add_argument("--iou", type=float, default=0.3, help="IoU 匹配阈值")
    pv.set_defaults(func=cmd_eval)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
