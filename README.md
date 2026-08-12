# Seed 2.1 VLM Hook Prompt Benchmark

这是一个面向客户交付的 **短剧 Hook Prompt 优化测试项目**。

它解决的是一个非常具体的问题：

- 用火山方舟 VLM 模型理解短剧视频；
- 提取视频里的 **Hook（钩子点）**；
- 用同一套 benchmark 评估不同 prompt 版本；
- 让后续优化结果能稳定对比，而不是每次重新人肉判断。

本项目 **只关注 hook**，不关注 highlights。

---

## 项目价值

客户拿到这个仓库后，可以直接做三件事：

1. 用自己的 API Key 和模型 Endpoint ID 运行现有 prompt；
2. 新增自己的 prompt 版本做批量测试；
3. 直接查看 benchmark 分数，判断优化有没有变好。

换句话说，这不是一个“演示脚本”，而是一套可以直接复用的 **prompt 测试与评估基线**。

---

## 交付内容

仓库里已经包含：

- 7 个短剧 case 的测试输入；
- `v1`、`v1.2`、`v1.3`、`v1.4` 四版 prompt；
- 一份正式 benchmark；
- 自动评估脚本；
- 一组可直接参考的 baseline 结果。

客户下载后，不需要再从零搭框架，只需要：

- 填自己的 API Key；
- 填自己的模型 Endpoint ID；
- 运行命令；
- 看评估报告。

---

## 三步开始

### 第一步：安装依赖

```bash
pip install -r requirements.txt
```

### 第二步：填入你自己的配置

```bash
cp .env.example .env
```

然后：

- 在 `.env` 里填你自己的 `ARK_API_KEY`
- 在 `config/cases.yaml` 里填你自己的模型 `Endpoint ID`

### 第三步：运行并评估

```bash
cd src
python -m hook_extractor.cli extract --all --prompt v1.4 --model seed-2-1-turbo
python -m hook_extractor.cli eval --run results/v1.4_seed-2-1-turbo
```

跑完后，直接看：

- `results/<prompt>_<model>/_eval.md`

---

## 客户最该看什么

评估报告里，最重要的是顶部的 **Benchmark 达成度**。

优先看这 3 个值：

- **综合分**
- **绿色保留率**
- **红色误命中数**

如果一个新 prompt：

- 绿色保留住了；
- 红色 badcase 明显减少了；

那它就是更好的版本。

---

## 先看结论：这个项目怎么评估 prompt

后续任何 prompt 版本，统一和 `data/benchmark/benchmark.json` 比较。

这份 benchmark 的来源是：

- 使用 **Seed 2.1 Turbo** 模型；
- 配合 **v1 版提示词**；
- 跑出一版 hook 时间戳结果；
- 再对这些结果进行**人工研判**；
- 最终整理成后续 prompt 迭代统一使用的 benchmark。

benchmark 的规则是：

| 人工研判颜色 | 含义 | 后续版本目标 |
| --- | --- | --- |
| 绿色 `good` | 这是明确应该保留的优质 hook | **尽量保留**，允许少量时间偏差 |
| 红色 `bad` | 这是明显不该输出的 badcase | **必须删除** |
| 黄色 `borderline` | 这个点勉强可用，但时间微调会更好 | 可保留，可优化 |
| 白色 `acceptable` | 可删可留 | 中性 |

因此，后续优化的核心目标不是“多出几个结果”，而是：
- **保住绿色**；
- **删掉红色**；
- **黄色能微调更好**；
- **白色无强约束**。

项目里已经把这套规则固化成 benchmark 评分。

---

## Benchmark 怎么打分

核心分数：

```text
benchmark_score = 100 × (0.5 × 绿色保留率 + 0.5 × 红色规避率)
```

解释：
- **绿色保留率**：模型有没有保住那些真正该保留的 hook；
- **红色规避率**：模型有没有删掉那些明显不该输出的 badcase。

黄色 / 白色只展示，不计入核心分数。

也就是说，这个项目的评估重点是 **语义质量**，不是单纯拼时间戳精度。
时间误差仍然会统计，但它是辅助指标，不是主指标。

---

## 项目结构

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── config/
│   ├── cases.yaml            # case 视频 + 模型别名（公开仓库用占位 Endpoint ID）
│   └── cases.local.yaml      # 你自己的真实 Endpoint ID（本地新建，已 gitignore，不提交）
├── prompts/
│   ├── v1.txt
│   ├── v1.2.txt
│   ├── v1.3.txt
│   ├── v1.4.txt
│   └── segment_analysis.txt  # 片段视频分析提示词（喂给 Seed 2.1 Pro，迭代的核心）
├── data/
│   ├── annotations/
│   │   └── annotations.json
│   └── benchmark/
│       └── benchmark.json
├── scripts/
│   └── build_benchmark.py
├── src/
│   └── hook_extractor/
│       ├── config.py
│       ├── ark_client.py       # Turbo 提取 hook + Pro 分析片段（base64 传视频）
│       ├── evaluator.py
│       ├── segment_analyzer.py # ffmpeg 剪 badcase 片段 + 调 Pro 视频理解
│       └── cli.py              # extract / eval / analyze 三个子命令
└── results/
```

关键文件：
- `prompts/`：存放各版本 hook 提取 prompt，以及片段分析提示词 `segment_analysis.txt`。
- `data/benchmark/benchmark.json`：后续所有版本统一对比的标准答案。
- `results/`：每次运行的输出、评估报告（`_eval.md`）与片段分析报告（`_segment_analysis.md`）。
- `config/cases.yaml`：case 视频地址 + 模型别名映射（公开占位）；真实 Endpoint ID 放本地 `config/cases.local.yaml`。

---

## 使用前你必须先填的配置

### 1. API Key

复制配置文件：

```bash
cp .env.example .env
```

然后在 `.env` 中填入你自己的：

```bash
ARK_API_KEY=your_ark_api_key_here
```

### 2. 模型 Endpoint ID

编辑 `config/cases.yaml`，把下面这些占位值替换成你自己的模型 Endpoint ID：

```yaml
models:
  seed-2-1-pro: "your_seed_2_1_pro_endpoint_id"
  seed-2-1-turbo: "your_seed_2_1_turbo_endpoint_id"
  seed-evolving: "your_seed_evolving_endpoint_id"
```

**注意：本仓库不会包含任何真实 API Key 或真实 Endpoint ID。**
你需要使用你自己火山方舟账号下的配置。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置密钥和模型

```bash
cp .env.example .env
# 然后手动编辑 .env 和 config/cases.yaml
```

### 3. 运行单个 case

```bash
cd src
python -m hook_extractor.cli extract --case case1 --prompt v1.4 --model seed-2-1-turbo
```

### 4. 跑全部 case

```bash
cd src
python -m hook_extractor.cli extract --all --prompt v1.4 --model seed-2-1-turbo
```

### 5. 生成评估报告

```bash
cd src
python -m hook_extractor.cli eval --run results/v1.4_seed-2-1-turbo
```

---

## 输出结果怎么看

每次运行会在 `results/<prompt>_<model>/` 下生成两类文件：

1. `case*.json`
   - 每个视频一个结果文件；
   - 包含模型输出的 hook 结果。

2. `_eval.md`
   - 自动生成的评估报告；
   - 报告顶部是 **Benchmark 达成度（核心）**；
   - 后面是时间戳对齐指标（辅助）。

看报告时，优先看这三个值：
- **综合分**
- **绿色保留率**
- **红色误命中数**

---

## Prompt 版本说明

| 文件 | 用途 | benchmark 综合分 |
| --- | --- | --- |
| `prompts/v1.txt` | 原始版 prompt（benchmark 来源） | 50.0 |
| `prompts/v1.2.txt` | 客户基于 v1 自行优化：收紧 hook 定义 + 8 步验证流程 | — |
| `prompts/v1.3.txt` | **v1.2 × v3 融合**：保留 v1.2 双输出+8步流程，融入 E1-E4/P1/三力 | 55.0 |
| `prompts/v1.4.txt` | **自动化迭代终版**：hook-only + 三力 + **E1-E7** + P1；红色误命中 15→1 | **71.7** |

> 完整测试报告见 [`reports/Seed_2.1_Turbo_v1.4_测试报告.html`](reports/Seed_2.1_Turbo_v1.4_测试报告.html)（关键指标、优化效果、v1→v1.4 提示词改动、v1.4 完整稿）。
>
> 注：`v2` / `v3` 为中间迭代版本，结果已沉淀进 `v1.3` / `v1.4`，源文件已从仓库移除。

你也可以新增自己的版本，例如：

```text
prompts/v4.txt
prompts/customer_a_v1.txt
prompts/ablation_no_badcase_filter.txt
```

然后直接运行：

```bash
python -m hook_extractor.cli extract --all --prompt v4 --model seed-2-1-turbo
python -m hook_extractor.cli eval --run results/v4_seed-2-1-turbo
```

---

## 自动化迭代（Turbo 提取 → benchmark 对比 → Pro 诊断片段 → 产出新 prompt）

本项目内置一条**闭环自动迭代流水线**，让 prompt 优化不靠拍脑袋，而是靠"让 Pro 亲眼看 badcase 视频片段"给出可执行改法。三步：

```bash
cd src

# ① 用 Turbo + 当前最新 prompt 跑全部 case，得到 hook 时间戳
python -m hook_extractor.cli extract --all --prompt v1.4 --model seed-2-1-turbo

# ② 对比 benchmark，报告顶部给出综合分、绿色漏保留、红色误命中
python -m hook_extractor.cli eval --run results/v1.4_seed-2-1-turbo

# ③ 对每个 badcase：ffmpeg 剪出片段 → base64 送 Seed 2.1 Pro + 片段分析提示词做视频理解
#    Pro 判定该片段该保留还是删除、为什么、以及 hook 提取提示词该怎么改
python -m hook_extractor.cli analyze --run results/v1.4_seed-2-1-turbo
```

`analyze` 会产出 `results/<run>/_segment_analysis.md`（人读）与 `_segment_analysis.json`（结构化）。
你把里面的 `prompt_improvement` 建议汇总，就能写出下一版 prompt。

**为什么用两个模型分工**：
- **Seed 2.1 Turbo**：跑全片、提取 hook 时间戳（主模型，量大求快）。
- **Seed 2.1 Pro**：只对剪出来的**单个 badcase 短片段**做深度视频理解（贵但准，用量小）。
- **`prompts/segment_analysis.txt`（片段视频分析提示词）**：整条流水线的灵魂。它不让 Pro "复述剧情"，而是把"人工研判钩子好坏"翻译成一套可执行的视频理解任务——客观描述 → 定位结束瞬间 → 三力检验 → badcase 命中判断 → keep/drop 判定 → 与人工研判对齐 → 反推提示词改法。改这个文件，基本等于改整个自动迭代的效果。

这套自动化迭代在中间阶段曾产出 `v2` / `v3`，当前已经把有效规则合并进最终保留的 `v1.3` / `v1.4`。当时从 badcase 片段里提炼出的关键规则包括：
- **E1** 高潮后失利方发怒/部署求援的过渡节点 → 删；
- **E2** "行动后等待结果"停在无征兆的空等初期 → 删；
- **E3** 真相已说全、即时反应已现，后面只剩补充性尾句 → 删；
- **E4** 只是主角"察觉异常→戒备"的心理活动收尾、外部冲突未爆发 → 删；
- **P1**（保护）主角锁定追责对象、放狠话+下令启动关键行动、真相未揭晓 → 必须保留（防误删绿色）。

这些规则后来继续扩展为 `v1.4` 中的 E1-E7 + P1。

---

## 如果你要更新 benchmark

benchmark 不是手写的，而是从人工标注自动生成的。

如果你调整了 `data/annotations/annotations.json`，可以重建 benchmark：

```bash
python scripts/build_benchmark.py
```

---

## 模型调用说明

本项目默认通过火山方舟 Chat Completions 接口调用视频理解能力，视频以 `video_url` 形式传入，`fps` 控制抽帧率。

抽帧率建议：
- `1.0 ~ 2.0`：比较稳妥；
- fps 越高，时间更细，但 token / 耗时也会更高。

视频调用逻辑在 `src/hook_extractor/ark_client.py`。

---

## 给客户的提醒

1. **请务必填入你自己的 API Key。**
2. **请务必填入你自己的模型 Endpoint ID。**
3. `.env` 不要提交到 GitHub。
4. 如果你新增了 prompt，建议直接用 benchmark 做横向比较，不要只凭主观感觉看结果。

---

## 许可证 / 使用说明

本仓库用于 Prompt 优化测试与 benchmark 对比演示。
如需对外扩展，请根据你自己的业务场景补充说明与合规配置。
