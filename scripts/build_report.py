"""生成《Seed 2.1 Turbo + 提示词 v1.4 测试报告》HTML。
数据来自本仓库各 run 的 _eval.md（v1/v2/v1.3/v1.4）与片段分析报告；v1.4 提示词全文
直接读取 prompts/v1.4.txt 以保证与实际使用完全一致。"""
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V14_PROMPT = (ROOT / "prompts" / "v1.4.txt").read_text(encoding="utf-8")

# ---- 各版本 benchmark 汇总（均为 7 case 全量实测；v1 为 benchmark 来源）----
VERSIONS = [
    # name, score, green_kept, green_total, red_hit, red_total, note
    ("v1（原始版·benchmark来源）", 50.0, 2, 2, 15, 15, "松散召回，无验证链/无 badcase 排除；红色全部保留"),
    ("v1.3（v1.2×v3 融合）", 55.0, 1, 2, 6, 15, "恢复双输出+8步流程+E1-E4；召回偏宽，红色仍漏 6"),
    ("v2（聚焦hook+badcase门槛）", 61.7, 1, 2, 4, 15, "hook-only + 三力 + E1-E4"),
    ("v1.4（自动迭代终版）", 71.7, 1, 2, 1, 15, "hook-only + 三力 + E1-E7 + P1；红色仅漏 1"),
]

# v1.4 逐 case（预测数 / 绿保留 / 红误命中 / 黄保留 / 白保留）
V14_CASES = [
    ("case1", "蒙眼望断江南雪", 8, "0/0", "0/1", 0, 1),
    ("case2", "渔乡守真心", 6, "1/1", "1/4", 0, 0),
    ("case3", "一次伸手，一生情", 8, "0/1", "0/3", 0, 2),
    ("case4", "新娘当场换新郎", 5, "0/0", "0/2", 1, 1),
    ("case5", "爷爷不请七遍不动筷", 6, "0/0", "0/2", 0, 1),
    ("case6", "狐狸抬轿", 6, "0/0", "0/2", 1, 3),
    ("case7", "别怪我心狠，谁让你动我三十万鱼苗", 3, "0/0", "0/1", 0, 0),
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


def esc(s: str) -> str:
    return html.escape(s)


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
    f"<tr><td>{esc(cid)}</td><td>{esc(nm)}</td><td class='num'>{npred}</td>"
    f"<td class='num'>{g}</td><td class='num red'>{r}</td><td class='num'>{y}</td><td class='num'>{w}</td></tr>"
    for cid, nm, npred, g, r, y, w in V14_CASES
)

diff_rows = "".join(
    f"<tr><td class='dim'>{esc(dim)}</td><td class='v1cell'>{esc(a)}</td><td class='v14cell'>{esc(b)}</td></tr>"
    for dim, a, b in DIFFS
)

rule_rows = "".join(
    f"<tr><td class='tag'>{esc(code)}</td><td class='muted'>{esc(src)}</td><td>{esc(desc)}</td></tr>"
    for code, src, desc in RULES
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
    --v14:#37d67a;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:linear-gradient(160deg,#0d1020,#141833 60%,#0f1328);
    color:var(--ink); font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
    line-height:1.65; }}
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
  section {{ background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:26px 28px; margin:22px 0; }}
  section h2 {{ font-size:20px; margin:0 0 16px; display:flex; align-items:center; gap:10px; }}
  section h2 .n {{ background:var(--blue); color:#fff; width:26px; height:26px; border-radius:8px;
    display:inline-flex; align-items:center; justify-content:center; font-size:14px; }}
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
  footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:34px; }}
  @media (max-width:720px) {{ .kpis{{grid-template-columns:repeat(2,1fr);}} .cols{{grid-template-columns:1fr;}} }}
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
      <span class="pill">7 个短剧 · benchmark 54 条 hook</span>
      <span class="pill">评测口径：绿色保留率 + 红色规避率</span>
    </div>
  </header>

  <div class="kpis">
    <div class="kpi win"><div class="big">71.7</div><div class="lab">v1.4 综合分 / 100</div><div class="delta up">▲ 相比 v1 +21.7</div></div>
    <div class="kpi win"><div class="big">93%</div><div class="lab">红色 badcase 规避率</div><div class="delta up">▲ v1 为 0%</div></div>
    <div class="kpi"><div class="big">1<span class="muted" style="font-size:18px">/15</span></div><div class="lab">红色误命中（越低越好）</div><div class="delta up">▼ v1 为 15/15</div></div>
    <div class="kpi"><div class="big">42</div><div class="lab">v1.4 输出 hook 总数</div><div class="delta muted">v1 为 54，更精不滥</div></div>
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
    <h2><span class="n">2</span>优化效果：v1.4 逐 case 明细</h2>
    <p class="lead">红色误命中集中清零；仅 case2「按手印被传送到海岛」这一设定奇观类片段仍被保留（1/15）。</p>
    <table>
      <thead><tr><th>Case</th><th>剧名</th><th class="num">预测数</th><th class="num">🟢保留</th><th class="num">🔴误命中</th><th class="num">🟡保留</th><th class="num">⬜保留</th></tr></thead>
      <tbody>{case_rows}</tbody>
    </table>
    <div class="note" style="margin-top:16px">时间戳对齐（辅助指标）：加权均 IoU 0.583、加权类型准确率 75%。本项目的评测核心是“语义判准”而非时间精度，故 IoU 类指标仅作参考。</div>
  </section>

  <section>
    <h2><span class="n">3</span>自动化迭代是怎么产出 v1.4 的</h2>
    <div class="flow">
      <span class="step">① Turbo + 当前 prompt 提取 hook</span><span class="arrow">→</span>
      <span class="step">② 与 benchmark 对比，挑出 badcase</span><span class="arrow">→</span>
      <span class="step">③ ffmpeg 剪出 badcase 片段</span><span class="arrow">→</span>
      <span class="step">④ Seed 2.1 Pro 视频理解逐条诊断</span><span class="arrow">→</span>
      <span class="step">⑤ 反推排除/保护规则，写入新 prompt</span>
    </div>
    <p class="lead" style="margin-top:14px">v1.3（55.0 分）的 7 个 badcase 片段送 Pro 逐一“亲眼看片判断”，Pro 判定与人工研判 <b>100% 一致</b>，提炼出以下规则（E5-E7 为本轮新增）：</p>
    <table>
      <thead><tr><th>规则</th><th>来源</th><th>命中即删除 / 保留的情形</th></tr></thead>
      <tbody>{rule_rows}</tbody>
    </table>
  </section>

  <section>
    <h2><span class="n">4</span>提示词改动：v1 → v1.4</h2>
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
    <h2><span class="n">5</span>最终版提示词 v1.4（完整稿）</h2>
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

out = ROOT / "reports" / "Seed_2.1_Turbo_v1.4_测试报告.html"
out.write_text(HTML, encoding="utf-8")
print("written:", out, "bytes:", len(HTML))
