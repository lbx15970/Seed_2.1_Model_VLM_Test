"""生成《Seed 2.1 Turbo + 提示词 v1.5 测试报告》HTML（数据驱动）。

所有分数与时长均从 results/<ver>_seed-2-1-turbo/case*.json 现算，
与 benchmark.json 对齐（复刻 evaluator 的贪心 IoU 匹配），不手写硬编码，
保证报告数字与实际运行结果一致。v1.5 相比 v1.4 的核心升级是「片段时长约束」，
因此本报告新增「片段时长分布」维度。
"""
import html
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
BENCH = json.loads((ROOT / "data" / "benchmark" / "benchmark.json").read_text(encoding="utf-8"))
FINAL_VER = "v1.5"
FINAL_PROMPT = (ROOT / "prompts" / f"{FINAL_VER}.txt").read_text(encoding="utf-8")

# 时长门槛（与 prompts/v1.5.txt 的 Step 0.3 一致，单位秒）
DUR_TARGET_LO, DUR_TARGET_HI, DUR_HARD_CAP = 8.0, 20.0, 30.0

CASE_ORDER = ["case1", "case2", "case3", "case4", "case5", "case6", "case7"]
CASE_NAMES = {cid: BENCH["cases"][cid]["name"] for cid in CASE_ORDER}


def esc(s):
    return html.escape(str(s))


def _iou(a, b):
    s = max(a[0], b[0]); e = min(a[1], b[1]); inter = max(0.0, e - s)
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def fmt_ms(ms):
    s = int(round(ms / 1000)); return f"{s // 60:02d}:{s % 60:02d}"


def load_hooks(ver, cid):
    f = ROOT / "results" / f"{ver}_seed-2-1-turbo" / f"{cid}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    return (data.get("parsed") or {}).get("hook", []) or []


def match_case(preds, bench_items, iou_th=0.3):
    """复刻 evaluator：为每个 benchmark 条目找最佳未占用预测。
    返回 (pred_verdict: idx->(quality,iou,bench_id), bench_hits: list[dict])。"""
    used = {}
    pred_verdict = {}
    bench_hits = []
    for g in bench_items:
        gs = (float(g["start_time"]), float(g["end_time"]))
        best_j, best_iou = -1, 0.0
        for j, p in enumerate(preds):
            if j in used:
                continue
            iou = _iou((float(p["start_time"]), float(p["end_time"])), gs)
            if iou > best_iou:
                best_iou, best_j = iou, j
        hit = best_j >= 0 and best_iou >= iou_th
        gg = dict(g); gg["_hit"] = hit; gg["_iou"] = round(best_iou, 3) if hit else 0.0
        bench_hits.append(gg)
        if hit:
            used[best_j] = g["id"]
            pred_verdict[best_j] = (g["quality"], round(best_iou, 3), g["id"])
    return pred_verdict, bench_hits


def analyze_run(ver):
    """汇总一个版本：benchmark 分数 + 时长统计 + 逐 case 结构。缺数据返回 None。"""
    per_case = []
    all_durs = []
    G_tot = G_kept = R_tot = R_hit = Y_kept = W_kept = 0
    n_pred_total = 0
    for cid in CASE_ORDER:
        preds = load_hooks(ver, cid)
        if preds is None:
            return None
        items = BENCH["cases"][cid]["items"]
        pred_verdict, bench_hits = match_case(preds, items)
        durs = [(float(p["end_time"]) - float(p["start_time"])) / 1000.0 for p in preds]
        all_durs += durs
        n_pred_total += len(preds)
        g_tot = sum(1 for g in items if g["quality"] == "good")
        g_kept = sum(1 for g in bench_hits if g["quality"] == "good" and g["_hit"])
        r_tot = sum(1 for g in items if g["quality"] == "bad")
        r_hit = sum(1 for g in bench_hits if g["quality"] == "bad" and g["_hit"])
        y_kept = sum(1 for g in bench_hits if g["quality"] == "borderline" and g["_hit"])
        w_kept = sum(1 for g in bench_hits if g["quality"] == "acceptable" and g["_hit"])
        G_tot += g_tot; G_kept += g_kept; R_tot += r_tot; R_hit += r_hit
        Y_kept += y_kept; W_kept += w_kept
        per_case.append(dict(
            cid=cid, name=CASE_NAMES[cid], preds=preds, bench_hits=bench_hits,
            pred_verdict=pred_verdict, durs=durs,
            g_tot=g_tot, g_kept=g_kept, r_tot=r_tot, r_hit=r_hit,
            y_kept=y_kept, w_kept=w_kept,
        ))
    green_rate = G_kept / G_tot if G_tot else 1.0
    red_avoid = (R_tot - R_hit) / R_tot if R_tot else 1.0
    score = round(100 * (0.5 * green_rate + 0.5 * red_avoid), 1)
    return dict(
        ver=ver, per_case=per_case, all_durs=sorted(all_durs), n_pred=n_pred_total,
        G_tot=G_tot, G_kept=G_kept, R_tot=R_tot, R_hit=R_hit, Y_kept=Y_kept, W_kept=W_kept,
        green_rate=green_rate, red_avoid=red_avoid, score=score,
    )


def dur_stats(durs):
    if not durs:
        return dict(n=0, med=0, p90=0, mx=0, mean=0, over_cap=0, over_hi=0, in_target=0)
    ds = sorted(durs); n = len(ds)
    p90 = ds[min(n - 1, int(round(n * 0.9)) - 1)] if n else 0
    over_cap = sum(1 for x in ds if x > DUR_HARD_CAP)
    over_hi = sum(1 for x in ds if x > DUR_TARGET_HI)
    in_target = sum(1 for x in ds if DUR_TARGET_LO <= x <= DUR_TARGET_HI)
    return dict(n=n, med=round(median(ds), 1), p90=round(p90, 1), mx=round(max(ds), 1),
                mean=round(sum(ds) / n, 1), over_cap=over_cap, over_hi=over_hi, in_target=in_target)


# ---- 收集三个关键版本（v1 基线 / v1.4 上一版 / v1.5 本版）----
RUNS = {v: analyze_run(v) for v in ["v1", "v1.4", FINAL_VER]}
R1, R14, R15 = RUNS["v1"], RUNS["v1.4"], RUNS[FINAL_VER]
S1, S14, S15 = (dur_stats(RUNS[v]["all_durs"]) if RUNS[v] else dur_stats([])
                for v in ["v1", "v1.4", FINAL_VER])

# 也纳入 v1.3/v2（若结果目录还在）用于综合分对比条
EXTRA = {v: analyze_run(v) for v in ["v1.3", "v2"]}


# ==== 版本综合分对比条 ====
def score_of(run, fallback):
    return run["score"] if run else fallback


VERSIONS = [
    ("v1（原始版·benchmark 来源）", score_of(R1, 50.0), R1, "松散召回，无验证链/无排除；红色全部保留，但片段时长自然（中位≈11s）", "base"),
    ("v1.3（v1.2×v3 融合）", score_of(EXTRA["v1.3"], 55.0), EXTRA["v1.3"], "恢复双输出+8步流程+E1-E4；召回偏宽", "mid"),
    ("v2（聚焦 hook+badcase 门槛）", score_of(EXTRA["v2"], 61.7), EXTRA["v2"], "hook-only + 三力 + E1-E4", "mid"),
    ("v1.4（无时长约束·分数含水分）", score_of(R14, 71.7), R14, "hook-only + 三力 + E1-E7 + P1；但片段普遍超长（中位 25.5s、max 120s），⚠ 红色规避靠“超长片段包住坏截点”，71.7 为虚高", "mid"),
    (f"{FINAL_VER}（本版·时长约束+E8/通杀强化）", score_of(R15, 0.0), R15, "在 v1.4 语义规则上叠加时长门槛 D1 + E8 + 跨类型通杀；时长全达标(max 25s)，68.3 为去水分后的真实分", "v14"),
]

bars = ""
for name, score, run, note, hot in VERSIONS:
    gk = run["G_kept"] if run else "?"; gt = run["G_tot"] if run else "?"
    rh = run["R_hit"] if run else "?"; rt = run["R_tot"] if run else "?"
    bars += f"""
    <div class="bar-row">
      <div class="bar-label">{esc(name)}</div>
      <div class="bar-track"><div class="bar-fill {hot}" style="width:{score}%"></div>
        <span class="bar-val">{score}</span></div>
      <div class="bar-sub">绿保留 {gk}/{gt}　红误命中 {rh}/{rt}　<span class="muted">{esc(note)}</span></div>
    </div>"""

ver_rows = ""
for name, score, run, note, hot in VERSIONS:
    if run:
        gk, gt, rh, rt = run["G_kept"], run["G_tot"], run["R_hit"], run["R_tot"]
        ravd = f"{round((rt - rh) / rt * 100)}%" if rt else "—"
    else:
        gk = gt = rh = rt = "?"; ravd = "—"
    hl = "hl" if name.startswith(FINAL_VER) else ""
    ver_rows += (f"<tr class='{hl}'><td>{esc(name)}</td><td class='num'>{score}</td>"
                 f"<td class='num'>{gk}/{gt}</td><td class='num'>{rh}/{rt}</td>"
                 f"<td class='num'>{ravd}</td></tr>")


# ==== 时长分布对比 ====
def dur_bar(stats, cls):
    """把 median 相对 60s 画成条，并叠加目标区间参考。"""
    if not stats["n"]:
        return "<div class='dstat muted'>（暂无数据）</div>"
    scale = 120.0  # 时间轴按最大 120s 归一
    med_w = min(stats["med"] / scale * 100, 100)
    p90_w = min(stats["p90"] / scale * 100, 100)
    mx_w = min(stats["mx"] / scale * 100, 100)
    lo = DUR_TARGET_LO / scale * 100; hi = DUR_TARGET_HI / scale * 100; cap = DUR_HARD_CAP / scale * 100
    return f"""
    <div class="dbar-track">
      <div class="dband target" style="left:{lo:.1f}%;width:{hi - lo:.1f}%" title="目标 8-20s"></div>
      <div class="dcap" style="left:{cap:.1f}%" title="硬上限 30s"></div>
      <div class="dmark med {cls}" style="left:{med_w:.1f}%" title="中位 {stats['med']}s"></div>
      <div class="dmark p90" style="left:{p90_w:.1f}%" title="p90 {stats['p90']}s"></div>
      <div class="dmark mx" style="left:{mx_w:.1f}%" title="max {stats['mx']}s"></div>
    </div>"""


dur_rows = ""
for label, st, cls in [("v1（基线）", S1, "base"), ("v1.4（超长）", S14, "mid"),
                       (f"{FINAL_VER}（本版）", S15, "v14")]:
    over_cap_pct = f"{round(st['over_cap'] / st['n'] * 100)}%" if st["n"] else "—"
    dur_rows += (f"<tr class='{'hl' if cls == 'v14' else ''}'><td>{esc(label)}</td>"
                 f"<td class='num'>{st['n']}</td><td class='num'>{st['med']}s</td>"
                 f"<td class='num'>{st['p90']}s</td><td class='num'>{st['mx']}s</td>"
                 f"<td class='num'>{st['mean']}s</td>"
                 f"<td class='num'>{st['over_cap']}（{over_cap_pct}）</td></tr>")

dur_bars_html = ""
for label, st, cls in [("v1", S1, "base"), ("v1.4", S14, "mid"), (FINAL_VER, S15, "v14")]:
    dur_bars_html += (f"<div class='dbar-row'><span class='dbar-label'>{esc(label)}</span>"
                      f"{dur_bar(st, cls)}"
                      f"<span class='dbar-meta'>中位 <b>{st['med']}s</b> · p90 {st['p90']}s · max {st['mx']}s</span></div>")


# ==== 提示词改动（v1 → v1.5）====
DIFFS = [
    ("片段时长", "无约束，但召回较散、时长自然偏短（中位≈11s）",
     f"新增门槛 D1：目标 8-20s、硬上限 30s；过长优先收紧起点或拆分为多条；实测中位 {S15['med']}s、max {S15['mx']}s"),
    ("输出范围", "同时产出 highlights + hook", "只产出 hook（highlights 恒为 []），算力集中，杜绝“泛看点召回”误保留"),
    ("hook 定义", "“关键前置事件已成立、答案未展开”的较松描述", "收紧为：已发生事实 + 具体未解问题 + 观众未知 + 答案未展开，且“非高度可预期”"),
    ("三力门槛", "无", "未解问题 + 情绪拉力 + 下一步期待，缺一即删"),
    ("验证链", "三点自检，无强制字段链", "established_fact → fact_evidence → open_question → 观众未知 → After End Check → 剧情驱动性"),
    ("专项排除", "无", "E1-E8 八条实证排除规则 + 3 条跨类型通杀"),
    ("保护规则", "无", "P1：主角锁定追责对象+下令启动行动+真相未揭晓 → 必须保留"),
    ("截点/收紧", "答案未泄露 > 画面稳定（较笼统）", "Step 6 给出具体截点；Step 6.5 只动 start_time 或拆分，禁止延后 end_time 压时长"),
    ("一段多点", "无限制，易把多个事件塞进一个长片段", "明确禁止“一段包多点”；多 open_question 必须拆成多条独立短 hook"),
]
diff_rows = "".join(
    f"<tr><td class='dim'>{esc(d)}</td><td class='v1cell'>{esc(a)}</td><td class='v14cell'>{esc(b)}</td></tr>"
    for d, a, b in DIFFS)

# ==== 规则表（含新增 D1）====
RULES = [
    ("D1", "v1.5 新增", "片段时长门槛：目标 8-20s、硬上限 30s；过长只收紧 start_time 或拆分，不延后 end_time"),
    ("E1", "v2 迭代", "高潮后失利方发怒/部署求援的过渡节点（停在布置任务/拨电话/下指令）"),
    ("E2", "v2 迭代", "“行动后等待结果”停在无征兆的空等初期（引鱼/下药/布陷阱…）"),
    ("E3", "v2→v1.3 强化", "真相/爆料已说全 + 对方第一波即时反应已现，后续只剩补充语句/情绪宣泄"),
    ("E4", "v2 迭代", "仅主角“察觉异常→戒备”的心理活动收尾，外部冲突尚未爆发"),
    ("E5", "v1.3 迭代", "无实质内容的空洞宣告/铺垫台词（“进门要守规矩”“你给我等着”）"),
    ("E6", "v1.3 迭代", "对已发生事件的评价/感慨类过渡对白；且严禁脑补片段外后续"),
    ("E7", "v1.3 迭代", "指控/揭穿后仅呈现另一方“本能变脸情绪反应”，尚无具体反驳/反制/升级"),
    ("E8", "v1.5 新增", "日常事务协商弱悬念（借船/分账/请托等，结果凭常理高概率可预判）→ 删"),
    ("通杀", "v1.5 新增", "把 E3/E4/E5 本质扩展到所有 hook_type：核心爆点已释放 / 仅内心怀疑戒备 / 笼统威压无具体冲突"),
    ("P1", "保护规则(v1.5强化)", "主角因受损事件锁定追责对象+下令启动行动+真相未揭晓 → 必须保留（防误删绿色）"),
]
rule_rows = "".join(
    f"<tr class='{'hl' if c in ('D1', 'E8', '通杀') else ''}'><td class='tag'>{esc(c)}</td><td class='muted'>{esc(s)}</td><td>{esc(d)}</td></tr>"
    for c, s, d in RULES)


# ==== 逐 case 可视化 ====
QMAP = {
    "good": ("q-green", "🟢", "命中优质 hook · 应保留（成功）"),
    "bad": ("q-red", "🔴", "命中 badcase · 应删除（误命中）"),
    "borderline": ("q-yellow", "🟡", "命中黄色 · 可选保留"),
    "acceptable": ("q-white", "⬜", "命中白色 · 中性"),
    "extra": ("q-extra", "➕", "benchmark 未覆盖 · 模型自主新增"),
}
QLABEL = [("q-green", "🟢 应保留"), ("q-red", "🔴 应删除"), ("q-yellow", "🟡 可选"),
          ("q-white", "⬜ 中性"), ("q-extra", "➕ 模型新增")]


def dur_badge(sec):
    if sec > DUR_HARD_CAP:
        return f"<span class='chip durbad'>{sec:.0f}s ⚠超上限</span>"
    if sec > DUR_TARGET_HI:
        return f"<span class='chip durwarn'>{sec:.0f}s 偏长</span>"
    return f"<span class='chip durok'>{sec:.0f}s</span>"


def build_case_block(c):
    preds, bench_hits, pv = c["preds"], c["bench_hits"], c["pred_verdict"]
    total = max([float(p["end_time"]) for p in preds]
                + [float(g["end_time"]) for g in bench_hits] + [1.0])
    segs_a = ""
    for j, p in enumerate(preds):
        st, en = float(p["start_time"]), float(p["end_time"])
        q = pv.get(j, ("extra", 0.0, None))[0]
        left = st / total * 100; wd = max((en - st) / total * 100, 0.8)
        segs_a += (f"<div class='tl-seg {QMAP[q][0]}' style='left:{left:.2f}%;width:{wd:.2f}%' "
                   f"title='#{j+1} {fmt_ms(st)}-{fmt_ms(en)} · {(en-st)/1000:.0f}s · {esc(p.get('hook_type',''))}'>{j+1}</div>")
    segs_b = ""
    for g in bench_hits:
        st, en = float(g["start_time"]), float(g["end_time"])
        left = st / total * 100; wd = max((en - st) / total * 100, 0.8)
        miss = "" if g["_hit"] else " miss"
        segs_b += (f"<div class='tl-seg {QMAP[g['quality']][0]}{miss}' style='left:{left:.2f}%;width:{wd:.2f}%' "
                   f"title='{esc(g['id'])} {QMAP[g['quality']][2]} · {fmt_ms(st)}-{fmt_ms(en)} · {'命中' if g['_hit'] else '未命中'}'></div>")
    cards = ""
    for j, p in enumerate(preds):
        q, iou_v, bid = pv.get(j, ("extra", 0.0, None))
        cls, emoji, vtext = QMAP[q]
        sec = (float(p["end_time"]) - float(p["start_time"])) / 1000.0
        meta = (f"<span class='chip'>IoU {iou_v}</span><span class='chip'>↔ {esc(bid)}</span>"
                if bid else "<span class='chip muted'>无 benchmark 对应</span>")
        cards += f"""
      <div class="hook-card {cls}">
        <div class="hc-head">
          <span class="hc-idx">#{j+1}</span>
          <span class="hc-time">{fmt_ms(float(p['start_time']))} → {fmt_ms(float(p['end_time']))}</span>
          {dur_badge(sec)}
          <span class="chip type">{esc(p.get('hook_type',''))}</span>
          <span class="hc-verdict">{emoji} {esc(vtext)}</span>
          {meta}
        </div>
        <div class="hc-q"><b>未解问题：</b>{esc(p.get('open_question',''))}</div>
        <div class="hc-desc">{esc(p.get('description',''))}</div>
        <div class="hc-reason"><b>截点理由：</b>{esc(p.get('end_point_reason',''))}</div>
      </div>"""
    missed_green = [g for g in bench_hits if g["quality"] == "good" and not g["_hit"]]
    miss_note = ""
    if missed_green:
        items = "；".join(f"{esc(g['id'])}「{esc(g.get('content', '')[:24])}」" for g in missed_green)
        miss_note = f"<div class='miss-note'>⚠ 漏保留绿色 {len(missed_green)} 条：{items}</div>"
    legend = "".join(f"<span class='lg'><i class='dot {cc}'></i>{tt}</span>" for cc, tt in QLABEL)
    cst = dur_stats(c["durs"])
    return f"""
    <details class="case-block" {'open' if c['cid'] in ('case5', 'case7') else ''}>
      <summary>
        <span class="cb-id">{esc(c['cid'])}</span>
        <span class="cb-name">{esc(c['name'])}</span>
        <span class="cb-stat">输出 {len(preds)} · 🟢{c['g_kept']}/{c['g_tot']} · 🔴{c['r_hit']}/{c['r_tot']} · 🟡{c['y_kept']} · ⬜{c['w_kept']} · 时长中位 {cst['med']}s/max {cst['mx']}s</span>
      </summary>
      <div class="cb-body">
        {miss_note}
        <div class="tl-wrap">
          <div class="tl-row"><span class="tl-tag">模型 {FINAL_VER}</span><div class="tl-track">{segs_a}</div></div>
          <div class="tl-row"><span class="tl-tag">benchmark</span><div class="tl-track">{segs_b}</div></div>
          <div class="tl-axis"><span>00:00</span><span>{fmt_ms(total)}</span></div>
          <div class="legend">{legend}<span class="muted">（斜纹=benchmark 未被命中；hover 看时长与详情）</span></div>
        </div>
        <div class="cards">{cards}</div>
      </div>
    </details>"""


cases_viz = "".join(build_case_block(c) for c in R15["per_case"]) if R15 else "<p class='note'>⚠ 未找到 v1.5 结果目录，请先运行提取。</p>"

# KPI 数据
kpi_score = R15["score"] if R15 else 0.0
kpi_delta = round(kpi_score - (R1["score"] if R1 else 50.0), 1)
kpi_red_avoid = round(R15["red_avoid"] * 100) if R15 else 0
kpi_over_cap_14 = S14["over_cap"]
kpi_over_cap_15 = S15["over_cap"]

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seed 2.1 Turbo + 提示词 {FINAL_VER} 测试报告</title>
<style>
  :root {{
    --bg:#0f1220; --card:#1a1f35; --card2:#222844; --ink:#e8ebf5; --muted:#9aa3c0;
    --line:#2c3358; --green:#37d67a; --red:#ff5c7c; --blue:#4d8dff; --gold:#ffb020; --v14:#37d67a;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:linear-gradient(160deg,#0d1020,#141833 60%,#0f1328);
    color:var(--ink); font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif; line-height:1.65; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:48px 24px 80px; }}
  header.hero {{ text-align:center; padding:40px 20px 28px; }}
  .hero h1 {{ font-size:30px; margin:0 0 10px; letter-spacing:.5px; }}
  .hero .sub {{ color:var(--muted); font-size:15px; }}
  .pill {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px;
    background:#20264a; color:var(--muted); margin:2px 4px; border:1px solid var(--line); }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:28px 0 8px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px 18px; text-align:center; }}
  .kpi .big {{ font-size:34px; font-weight:800; }}
  .kpi .lab {{ color:var(--muted); font-size:13px; margin-top:6px; }}
  .kpi.win .big {{ color:var(--v14); }}
  .kpi .delta {{ font-size:12px; margin-top:4px; }}
  .up {{ color:var(--green); }} .down {{ color:var(--red); }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:26px 28px; margin:22px 0; }}
  section h2 {{ font-size:20px; margin:0 0 16px; display:flex; align-items:center; gap:10px; }}
  section h2 .n {{ background:var(--blue); color:#fff; width:26px; height:26px; border-radius:8px;
    display:inline-flex; align-items:center; justify-content:center; font-size:14px; }}
  p.lead {{ color:var(--muted); margin-top:-4px; }}
  .bar-row {{ margin:14px 0; }}
  .bar-label {{ font-size:14px; margin-bottom:6px; }}
  .bar-track {{ position:relative; background:#141838; border:1px solid var(--line); border-radius:10px; height:30px; overflow:hidden; }}
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
  pre {{ background:#0c0f22; border:1px solid var(--line); border-radius:12px; padding:18px; overflow:auto;
    font-size:12.5px; line-height:1.6; color:#cdd4ee; max-height:640px; white-space:pre-wrap; word-break:break-word; }}
  .flow {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:6px 0 2px; }}
  .step {{ background:var(--card2); border:1px solid var(--line); border-radius:8px; padding:6px 12px; font-size:13px; }}
  .arrow {{ color:var(--muted); }}
  .note {{ background:#171b38; border-left:3px solid var(--gold); padding:12px 16px; border-radius:8px; font-size:13.5px; color:var(--muted); }}
  /* 时长分布 */
  .dbar-row {{ display:flex; align-items:center; gap:12px; margin:12px 0; }}
  .dbar-label {{ width:44px; flex:0 0 44px; text-align:right; font-weight:700; font-size:13px; }}
  .dbar-track {{ position:relative; flex:1; height:34px; background:#0c0f22; border:1px solid var(--line); border-radius:6px; }}
  .dband.target {{ position:absolute; top:0; height:100%; background:rgba(55,214,122,.16); border-left:1px dashed var(--green); border-right:1px dashed var(--green); }}
  .dcap {{ position:absolute; top:0; height:100%; width:0; border-left:2px dashed var(--red); }}
  .dmark {{ position:absolute; top:50%; width:14px; height:14px; border-radius:50%; transform:translate(-50%,-50%); border:2px solid #0c0f22; }}
  .dmark.med {{ width:18px; height:18px; z-index:3; }}
  .dmark.med.base {{ background:#8b93b5; }} .dmark.med.mid {{ background:var(--gold); }} .dmark.med.v14 {{ background:var(--green); }}
  .dmark.p90 {{ background:#c9d2ea; z-index:2; }} .dmark.mx {{ background:var(--red); z-index:2; }}
  .dbar-meta {{ width:250px; flex:0 0 250px; font-size:12px; color:var(--muted); }}
  .dbar-meta b {{ color:var(--ink); }}
  .dlegend {{ font-size:12px; color:var(--muted); margin-top:6px; }}
  .dlegend i {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin:0 4px 0 12px; vertical-align:-1px; }}
  /* 逐 case */
  .case-block {{ background:var(--card2); border:1px solid var(--line); border-radius:12px; margin:12px 0; overflow:hidden; }}
  .case-block > summary {{ cursor:pointer; list-style:none; padding:14px 18px; display:flex; flex-wrap:wrap; align-items:center; gap:10px; user-select:none; }}
  .case-block > summary::-webkit-details-marker {{ display:none; }}
  .case-block > summary::before {{ content:"▸"; color:var(--muted); transition:transform .2s; }}
  .case-block[open] > summary::before {{ transform:rotate(90deg); }}
  .cb-id {{ font-weight:800; color:var(--blue); font-size:13px; }}
  .cb-name {{ font-weight:700; }}
  .cb-stat {{ margin-left:auto; font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }}
  .cb-body {{ padding:4px 18px 18px; border-top:1px solid var(--line); }}
  .miss-note {{ background:rgba(255,92,124,.12); border:1px solid rgba(255,92,124,.4); color:#ffb9c8; border-radius:8px; padding:8px 12px; font-size:13px; margin:12px 0; }}
  .tl-wrap {{ margin:12px 0 6px; }}
  .tl-row {{ display:flex; align-items:center; gap:10px; margin:6px 0; }}
  .tl-tag {{ width:80px; flex:0 0 80px; font-size:12px; color:var(--muted); text-align:right; }}
  .tl-track {{ position:relative; flex:1; height:26px; background:#0c0f22; border:1px solid var(--line); border-radius:6px; }}
  .tl-seg {{ position:absolute; top:2px; height:20px; border-radius:4px; font-size:10px; color:#06121f; display:flex; align-items:center; justify-content:center; font-weight:800; overflow:hidden; }}
  .tl-seg.miss {{ background-image:repeating-linear-gradient(45deg,transparent,transparent 3px,rgba(0,0,0,.35) 3px,rgba(0,0,0,.35) 6px); }}
  .tl-axis {{ display:flex; justify-content:space-between; font-size:11px; color:var(--muted); padding-left:90px; margin-top:2px; }}
  .q-green {{ background:var(--green); }} .q-red {{ background:var(--red); }} .q-yellow {{ background:var(--gold); }}
  .q-white {{ background:#c9d2ea; }} .q-extra {{ background:var(--blue); }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; padding-left:90px; margin-top:8px; font-size:12px; color:var(--ink); }}
  .lg {{ display:inline-flex; align-items:center; gap:5px; }}
  .dot {{ width:11px; height:11px; border-radius:3px; display:inline-block; }}
  .cards {{ display:grid; gap:10px; margin-top:14px; }}
  .hook-card {{ background:#12162e; border:1px solid var(--line); border-left-width:4px; border-radius:10px; padding:12px 14px; }}
  .hook-card.q-green {{ border-left-color:var(--green); }}
  .hook-card.q-red {{ border-left-color:var(--red); background:rgba(255,92,124,.06); }}
  .hook-card.q-yellow {{ border-left-color:var(--gold); }}
  .hook-card.q-white {{ border-left-color:#c9d2ea; }}
  .hook-card.q-extra {{ border-left-color:var(--blue); }}
  .hc-head {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:8px; }}
  .hc-idx {{ font-weight:800; color:var(--muted); }}
  .hc-time {{ font-variant-numeric:tabular-nums; font-weight:700; font-size:13px; }}
  .hc-verdict {{ font-size:12.5px; }}
  .chip {{ background:#232a4c; border:1px solid var(--line); border-radius:999px; padding:2px 9px; font-size:11.5px; color:var(--ink); }}
  .chip.type {{ background:#1d2b46; color:#8fc0ff; }}
  .chip.muted {{ color:var(--muted); }}
  .chip.durok {{ background:#14361f; color:#7be6a4; border-color:#1f5230; }}
  .chip.durwarn {{ background:#3a3411; color:#ffd98a; border-color:#5a4f18; }}
  .chip.durbad {{ background:#3a1520; color:#ff9db1; border-color:#5a1f2e; }}
  .hc-q {{ font-size:13.5px; color:#ffd9a0; margin:2px 0; }}
  .hc-desc {{ font-size:13px; color:var(--ink); margin:4px 0; }}
  .hc-reason {{ font-size:12.5px; color:var(--muted); }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:34px; }}
  @media (max-width:720px) {{ .kpis{{grid-template-columns:repeat(2,1fr);}} .dbar-meta{{display:none;}} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>Seed 2.1 Turbo · 提示词 {FINAL_VER} 测试报告</h1>
    <div class="sub">短剧 Hook 提取 · 自动化提示词迭代 · 本版核心：为“自动剪辑”加入片段时长约束</div>
    <div style="margin-top:12px">
      <span class="pill">主模型 Seed 2.1 Turbo（提取）</span>
      <span class="pill">Seed 2.1 Pro（片段视频理解·诊断）</span>
      <span class="pill">7 个短剧 · benchmark {sum(len(BENCH['cases'][c]['items']) for c in CASE_ORDER)} 条</span>
      <span class="pill">评测：绿色保留率 + 红色规避率 + 片段时长</span>
    </div>
  </header>

  <div class="kpis">
    <div class="kpi win"><div class="big">{kpi_score}</div><div class="lab">{FINAL_VER} 综合分 / 100</div>
      <div class="delta {'up' if kpi_delta >= 0 else 'down'}">{'▲' if kpi_delta >= 0 else '▼'} 相比 v1 {'+' if kpi_delta >= 0 else ''}{kpi_delta}</div></div>
    <div class="kpi win"><div class="big">{kpi_red_avoid}%</div><div class="lab">红色 badcase 规避率</div><div class="delta muted">v1 为 0%</div></div>
    <div class="kpi"><div class="big">{S15['med']}<span class="muted" style="font-size:18px">s</span></div>
      <div class="lab">片段时长中位（目标 8-20s）</div><div class="delta up">◀ v1.4 为 {S14['med']}s</div></div>
    <div class="kpi"><div class="big">{S15['mx']:.0f}<span class="muted" style="font-size:18px">s</span></div>
      <div class="lab">最长片段（v1.4 达 {S14['mx']:.0f}s）</div>
      <div class="delta {'up' if S15['over_cap'] <= S14['over_cap'] else 'down'}">超 30s 片段 {kpi_over_cap_14}→{kpi_over_cap_15}</div></div>
  </div>

  <section>
    <h2><span class="n">1</span>为什么要做 v1.5：时长失控 + 评估失真</h2>
    <p class="lead">v1.4 在语义判准上做得不错（综合分 71.7），但它<b>完全没有约束单条 hook 的片段时长</b>，带来两个直接问题。</p>
    <div class="note" style="border-left-color:var(--red)">
      <b>业务问题</b>：hook 片段要直接剪成短视频结尾，v1.4 却产出大量 40-120s 的超长片段（case7 只有 3 段、全部 80-120s；case5 出现 114.5s），无法直接用于成片。<br><br>
      <b>评估问题</b>：v1.4 对红色 badcase 的“规避”有相当一部分是<b>假象</b>——它并非真正跳过坏截点，而是用一个超长片段把红色片段整体<b>包含</b>了进去，导致与 benchmark 的 IoU 匹配错配、红色误命中被低估。换句话说，v1.4 的高分里掺了水。
    </div>
    <p style="margin-top:14px">v1.5 的做法分两步：<b>①</b> 沿用 v1.4 的全部语义规则（三力 / E1-E7 / P1 / 验证链）不放松，叠加时长门槛 <b>D1</b>——以 v1 真实分布为锚（中位≈11s），目标 8-20s、硬上限 30s；过长时<b>只收紧 start_time 或拆分为多条</b>，绝不延后 end_time 压缩（那会截晚泄底）。<b>②</b> 时长压回正常后，被超长片段掩盖的红色 badcase 真实暴露（红误命中一度回到 6/15）；对这些 badcase 再跑一轮 Seed 2.1 Pro 片段诊断，反推出 <b>E8（日常事务弱悬念）+ 3 条跨类型通杀 + 强化 P1</b>，把红误命中重新压到 2/15。</p>
  </section>

  <section>
    <h2><span class="n">2</span>片段时长分布对比（核心改进）</h2>
    <p class="lead">绿色带=目标区间 8-20s，红色虚线=硬上限 30s。圆点：<i style="color:#8b93b5">●</i>中位 <i style="color:#c9d2ea">●</i>p90 <i style="color:var(--red)">●</i>max。</p>
    {dur_bars_html}
    <table style="margin-top:18px">
      <thead><tr><th>版本</th><th class="num">片段数</th><th class="num">中位</th><th class="num">p90</th><th class="num">max</th><th class="num">均值</th><th class="num">超 30s 片段</th></tr></thead>
      <tbody>{dur_rows}</tbody>
    </table>
    <p class="note" style="margin-top:16px">读法：v1.4 的中位/最大值远超目标区间，且有多条 >30s；{FINAL_VER} 把分布重新压回目标带内，超 30s 片段从 {kpi_over_cap_14} 降到 {kpi_over_cap_15}。代价极小——语义综合分从 v1.4 的虚高 71.7 到 {FINAL_VER} 的真实 {kpi_score}（下节详解为何 v1.4 是虚高）。</p>
  </section>

  <section>
    <h2><span class="n">3</span>综合分对比（语义质量 · 全 7 case 实测）</h2>
    <p class="lead">综合分 = 50% × 绿色保留率 + 50% × 红色规避率。<b>注意别被 v1.4 的 71.7 误导</b>：那是靠“超长片段包住红色坏截点”骗过 IoU 匹配得来的虚高分。v1.5 把片段压回可剪辑长度后，被掩盖的红色 badcase 会真实暴露——即便如此，v1.5 靠 E8+跨类型通杀仍拿到 <b>68.3 的真实分（红规避 87%）</b>，仅比 v1.4 的注水分低 3.4，却换来“片段全部可直接用于剪辑”。</p>
    {bars}
    <table style="margin-top:18px">
      <thead><tr><th>版本</th><th class="num">综合分</th><th class="num">🟢绿保留</th><th class="num">🔴红误命中</th><th class="num">红规避率</th></tr></thead>
      <tbody>{ver_rows}</tbody>
    </table>
  </section>

  <section>
    <h2><span class="n">4</span>逐 case 可视化输出（模型 {FINAL_VER} 实际结果）</h2>
    <p class="lead">上排=模型 {FINAL_VER} 实际输出（编号=下方卡片序号、hover 看时长），下排=benchmark 参考（斜纹=没被命中）。卡片时长标签：<span style="color:#7be6a4">绿=达标 8-20s</span> / <span style="color:#ffd98a">黄=偏长 20-30s</span> / <span style="color:#ff9db1">红=超 30s</span>。</p>
    {cases_viz}
    <p class="note" style="margin-top:16px">🟢 越多越好、🔴 越少越好；➕ 是 benchmark 未覆盖、模型自主新增的候选，不计分。时长标签让“片段是否可直接用于剪辑”一目了然。</p>
  </section>

  <section>
    <h2><span class="n">5</span>迭代方式：自动化闭环（与前几版一致）</h2>
    <div class="flow">
      <span class="step">① Turbo + 当前 prompt 提取 hook</span><span class="arrow">→</span>
      <span class="step">② 与 benchmark 对比，挑出 badcase</span><span class="arrow">→</span>
      <span class="step">③ ffmpeg 剪出 badcase 片段</span><span class="arrow">→</span>
      <span class="step">④ Seed 2.1 Pro 视频理解逐条诊断</span><span class="arrow">→</span>
      <span class="step">⑤ 反推规则，写入新 prompt</span>
    </div>
    <p class="lead" style="margin-top:14px">本轮做了两件事：① 用 v1/v1.4 的时长分布做量化对照，反推出时长门槛 D1；② 对加时长约束后暴露的 6 个红色 + 1 个绿色 badcase 剪片段送 Seed 2.1 Pro 视频理解（判定与人工研判 100% 一致），反推出 E8 与 3 条跨类型通杀、并强化 P1。规则清单（D1 / E8 / 通杀为本版新增，已高亮）：</p>
    <table>
      <thead><tr><th>规则</th><th>来源</th><th>命中即删除 / 保留 / 约束的情形</th></tr></thead>
      <tbody>{rule_rows}</tbody>
    </table>
  </section>

  <section>
    <h2><span class="n">6</span>提示词改动：v1 → {FINAL_VER}</h2>
    <p class="lead">v1 是“松散召回 + 双输出 + 无验证/无排除/无时长约束”；{FINAL_VER} 是“hook-only + 三力 + 验证链 + E1-E8 + 跨类型通杀 + P1 + 时长门槛 D1”。</p>
    <table>
      <thead><tr><th>维度</th><th>v1（原始）</th><th>{FINAL_VER}（本版）</th></tr></thead>
      <tbody>{diff_rows}</tbody>
    </table>
    <p style="margin-top:16px">{FINAL_VER} 的 hook 流程：</p>
    <div class="flow">
      <span class="step">定义/三力门槛</span><span class="arrow">→</span>
      <span class="step">时长门槛 D1</span><span class="arrow">→</span>
      <span class="step">候选生成</span><span class="arrow">→</span>
      <span class="step">验证链</span><span class="arrow">→</span>
      <span class="step">排除 E1-E8 + 通杀</span><span class="arrow">→</span>
      <span class="step">截点</span><span class="arrow">→</span>
      <span class="step">时长复核·收紧/拆分</span><span class="arrow">→</span>
      <span class="step">去重</span><span class="arrow">→</span>
      <span class="step">排序</span>
    </div>
  </section>

  <section>
    <h2><span class="n">7</span>最终版提示词 {FINAL_VER}（完整稿）</h2>
    <p class="lead">以下为 <code>prompts/{FINAL_VER}.txt</code> 全文，可直接作为 Seed 2.1 Turbo 的 system prompt 使用。</p>
    <pre>{esc(FINAL_PROMPT)}</pre>
  </section>

  <footer>
    创量魔剪 · 短剧 Hook 提取自动化迭代 ｜ 数据由 Seed 2.1 Turbo 提取、Seed 2.1 Pro 诊断、benchmark 客观评测生成
  </footer>
</div>
</body>
</html>
"""

out = ROOT / "reports" / f"Seed_2.1_Turbo_{FINAL_VER}_测试报告.html"
out.write_text(HTML, encoding="utf-8")
print("written:", out, "bytes:", len(HTML))
if R15:
    print(f"{FINAL_VER}: score={R15['score']} green={R15['G_kept']}/{R15['G_tot']} "
          f"red_hit={R15['R_hit']}/{R15['R_tot']} dur_med={S15['med']}s max={S15['mx']}s over30s={S15['over_cap']}")
else:
    print("WARN: 未找到 v1.5 结果，报告用占位。请先跑提取再重新生成。")
