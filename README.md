# Seed 2.1 VLM Hook Prompt Benchmark

这是一个给客户使用的 **Prompt 优化测试项目**。

项目目标很简单：
- 用火山方舟 VLM 模型对短剧视频做理解；
- 提取视频里的 **Hook（钩子点）**；
- 用统一 benchmark 评估 prompt 版本优劣；
- 让后续提示词迭代可以稳定比较，不再靠人肉逐条判断。

本项目 **只关注 hook**，不关注 highlights。

---

## 你可以用它做什么

1. 配置你自己的 API Key 和模型 Endpoint ID。
2. 直接运行 `v1` / `v1.2` / `v2` 或你自己的 prompt。
3. 输出每个 case 的 hook 结果。
4. 自动与 benchmark 比较，得到一份清晰的评估报告。

这个项目适合做两类事：
- **prompt 迭代验证**：比较不同 prompt 版本效果；
- **客户自测**：下载后替换自己的 key / endpoint 即可跑。

---

## 先看结论：这个项目怎么评估 prompt

后续任何 prompt 版本，统一和 `data/benchmark/benchmark.json` 比较。

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
│   └── cases.yaml
├── prompts/
│   ├── v1.txt
│   ├── v1.2.txt
│   └── v2.txt
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
│       ├── ark_client.py
│       ├── evaluator.py
│       └── cli.py
└── results/
```

关键文件：
- `prompts/`：存放各版本 prompt。
- `data/benchmark/benchmark.json`：后续所有版本统一对比的标准答案。
- `results/`：每次运行的输出和评估报告。
- `config/cases.yaml`：case 视频地址 + 模型别名映射。

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
python -m hook_extractor.cli extract --case case1 --prompt v2 --model seed-2-1-turbo
```

### 4. 跑全部 case

```bash
cd src
python -m hook_extractor.cli extract --all --prompt v2 --model seed-2-1-turbo
```

### 5. 生成评估报告

```bash
cd src
python -m hook_extractor.cli eval --run results/v2_seed-2-1-turbo
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

| 文件 | 用途 |
| --- | --- |
| `prompts/v1.txt` | 原始版 prompt |
| `prompts/v1.2.txt` | 加强语义研判的版本 |
| `prompts/v2.txt` | 更聚焦 hook 和 badcase 过滤的版本 |

你也可以新增自己的版本，例如：

```text
prompts/v3.txt
prompts/customer_a_v1.txt
prompts/ablation_no_badcase_filter.txt
```

然后直接运行：

```bash
python -m hook_extractor.cli extract --all --prompt v3 --model seed-2-1-turbo
python -m hook_extractor.cli eval --run results/v3_seed-2-1-turbo
```

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
