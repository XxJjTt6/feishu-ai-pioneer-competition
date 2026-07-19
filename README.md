# Trend2SKU 爆款产品决策 Agent v2

> 名创优品「AI 驱动的产品开发智能决策引擎」命题原型：结构化决策输入 -> 趋势感知 -> 动态候选 -> 上市验证。

## 参赛信息

| 字段 | 已确认信息 |
|---|---|
| 队伍名称 | Saber |
| 成员人数 | 1 人 |
| 获知渠道 | 小红书 |

隐私授权仍须由参赛者本人在报名平台阅读条款后完成勾选；本仓库不代签、不推定授权。

## 先看数据与结论边界

仓库自带数据是固定种子 `20260719` 生成的 **400 条合成离线演示评论**：MINISO 140 条，POP MART、DAISO、MUJI、Flying Tiger 各 65 条。它们不是企业内部数据，不是真实用户评论、销售、毛利或试购记录，也不代表任何品牌的实际表现。

所有候选总分都是统一规则量表的 `xx/100`，**不是爆款概率**；模拟访谈接受度与模拟 NPS **不是实测购买或真实用户研究**。2026 年官方经营数字只用于说明决策规模与约束，不能直接推导单品需求、销量或 ROI。公开或企业数据接入前必须确认来源条款、授权、隐私和保存期限。

## v2 能做什么

Trend2SKU 在一次可审计运行中：

1. 接收九项结构化决策输入，并规范化为本轮唯一的 `decision_input`。
2. 对兴趣消费评论执行确定性方面分析，形成机会与证据索引。
3. 读取带日期和 URL 的趋势信号，拆解可比品牌并识别白空间。
4. 沿 VOC 需求、趋势主题、竞品白空间三条路径动态生成至少三个候选 SKU。
5. 按候选 ID 分别进行离线用户镜像验证与商品风险评估，不按数组位置串线。
6. 按八维固定权重评分并稳定排序；严重 IP 或质量风险不得直接 `GO`。
7. 输出榜首提案、风险条件、引用索引与 JSONL trace；可选 HITL 在决策点等待人工批准。

六类能力分别是趋势雷达、用户镜像、创意工坊、商品专家、爆款评审和提案生成。Agent 会真实经过只读工具注册表；远程模型只增强叙述，不控制数值评分、权重、阈值或风险闸口。

## 九项结构化输入

| 字段 | 含义 | 约束或示例 |
|---|---|---|
| `brief` | 决策简报 | Web 表单必填，最多 500 字符；旧 API 省略时使用确定性默认值 |
| `product_category` | 产品品类 | 毛绒、香氛配饰、文创文具、家居收纳、美妆工具、数码配件或其他 |
| `custom_category` | 自定义品类 | 最多 40 字符；仅当 `product_category=other` 时必填，否则规范化为空字符串 |
| `target_segment` | 目标客群 | 学生、年轻职场人、IP 粉丝、礼赠人群、亲子家庭或收藏玩家 |
| `target_market` | 目标市场 | 中国、东南亚、日韩、欧美、中东或全球 |
| `price_band` | 价格带 | 入门、中端或高端 |
| `ip_strategy` | IP 策略 | 原创、授权、不使用或待评估 |
| `objectives` | 决策目标 | 情绪价值、社交传播、毛利空间、供应链、本地化中选择 1 至 4 项；自动去重 |
| `constraints` | 约束条件 | 可选，最多 300 字符，可写成本、交期、材质、合规或区域限制 |

这些输入只改变候选生成、用户镜像、商品风险和报告上下文，**不会按字段向八维总分直接加分**。输入变化可能先改变候选特征或风险，再间接形成不同评分与排序；不存在“选择某市场即加分”或“多选目标即加分”的捷径。

## 快速开始

需要 Python 3.10+。运行依赖见 [`requirements.txt`](requirements.txt)，合成样本生成器见 [`data/make_sample.py`](data/make_sample.py)。下面以仓库根目录为当前目录：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python data/make_sample.py
PYTHONPATH=backend MINISO_LLM_PROVIDER=offline \
  .venv/bin/python -m miniso_studio.starter.cli run \
  --category interest_goods \
  --thread cli-demo-001 \
  --brief "生成兼顾情绪价值、社交传播、毛利和全球本地化的候选组合"
```

CLI 会打印候选排名，并在 `docs/generated/` 中创建新的版本化 Markdown 报告；若同名文件存在，不会原地覆盖。每次运行的 trace 位于调用方配置的运行目录。生产环境应为报告、trace 和 checkpoint 配置有权限、留存期限与清理策略的持久化存储。

## 浏览器工作台

```bash
PYTHONPATH=backend MINISO_LLM_PROVIDER=offline \
  .venv/bin/python -m uvicorn miniso_studio.starter.api:app \
  --host 127.0.0.1 --port 8767
```

浏览器打开 `http://127.0.0.1:8767`。表单提交九项输入；候选榜单切换会以同一个候选 ID 联动商品概念、八维得分、模拟访谈/NPS 和商品风险，不会误用其他候选的数据。

运行完成后，“完整运行报告”和“开题报告摘要”会在页面内的报告 `dialog` 中打开。两类报告均可下载 Markdown；“下载当前结果”会下载本次视图 JSON。下载内容绑定当前 `run_id`，开始新一轮运行时旧链接和旧内容会失效。

## 同步 API

健康检查：

```bash
curl -s http://127.0.0.1:8767/api/health
```

`POST /api/run` 的完整 v2 请求示例：

```bash
curl -s -X POST http://127.0.0.1:8767/api/run \
  -H 'Content-Type: application/json' \
  -d '{
    "brief": "为学生设计开学季社交文具",
    "product_category": "stationery",
    "custom_category": "",
    "target_segment": "student",
    "target_market": "southeast_asia",
    "price_band": "entry",
    "ip_strategy": "original",
    "objectives": ["social", "localization"],
    "constraints": "适配潮湿气候和校园渠道，单件包装",
    "category": "interest_goods",
    "hitl": false,
    "thread_id": "api-demo-001"
  }'
```

响应会返回独立的 `run_id`、`thread_id`、规范化后的 `decision_input`、候选及其联动验证结果。报告接口 **必须显式传入本次返回的 `run_id`**，不能依赖“最后一次运行”：

```bash
curl -s "http://127.0.0.1:8767/api/report?run_id=${RUN_ID}&kind=full"
curl -s "http://127.0.0.1:8767/api/report?run_id=${RUN_ID}&kind=opening"
```

服务进程只缓存最近 20 次运行。缓存过期、服务重启或 `run_id` 不存在时，报告接口返回 `404`；生产接入必须替换为受控持久化存储。

## SSE API

`GET /api/stream` 依次发送 `trace`、`result` 或 `error`，最后发送 `done`。关键 query 如下；`objectives` 是数组，因此需要重复同名 query：

```bash
curl -N --get http://127.0.0.1:8767/api/stream \
  --data-urlencode 'brief=设计香氛配饰礼盒' \
  --data-urlencode 'product_category=fragrance_accessory' \
  --data-urlencode 'custom_category=' \
  --data-urlencode 'target_segment=young_professional' \
  --data-urlencode 'target_market=global' \
  --data-urlencode 'price_band=premium' \
  --data-urlencode 'ip_strategy=evaluate' \
  --data-urlencode 'objectives=emotional' \
  --data-urlencode 'objectives=margin' \
  --data-urlencode 'constraints=礼盒可回收' \
  --data-urlencode 'thread_id=sse-demo-001' \
  --data-urlencode 'hitl=false'
```

同一连接的事件共享同一个 `run_id` 和 `thread_id`；并发运行互相隔离。客户端应校验事件身份，并在收到 `done`、错误或断线后关闭连接。

## 人工复核

命令行启用 HITL：

```bash
PYTHONPATH=backend MINISO_LLM_PROVIDER=offline MINISO_HITL=true \
  .venv/bin/python -m miniso_studio.starter.cli run \
  --thread pilot-review-001

PYTHONPATH=backend .venv/bin/python -m miniso_studio.starter.cli resume \
  --thread pilot-review-001
```

API 使用 `POST /api/run` 传入 `"hitl": true` 和唯一 `thread_id`，再以 `POST /api/resume` 提交 `{"thread_id":"pilot-review-001","action":"approve"}`。同一 thread 的重复运行、并发恢复和重复消费 checkpoint 会返回冲突，而不是静默覆盖状态。

## 八维评分

| 维度 | 权重 |
|---|---:|
| 趋势匹配 | 20% |
| 需求强度 | 20% |
| 差异化 | 15% |
| 社交传播 | 15% |
| 成本与毛利 | 10% |
| 供应链可行性 | 10% |
| IP/合规 | 5% |
| 全球本地化 | 5% |

总分 `>=75` 建议 `GO`，`60-74.99` 建议 `CONDITIONAL_GO`，`<60` 建议 `NO_GO`。严重 IP 或质量风险会阻止直接 `GO`。权重、阈值和确定性输入需要在获得企业历史候选与真实上市 outcome 后重新校准。

## qwen3.7-plus 在线叙述增强

默认 `offline` 不联网、不需要 API Key。在线 Coding Plan 主路径使用 Qwen 的 OpenAI-compatible `POST /chat/completions` 协议，完整配置模板见 [`.env.example`](.env.example)；`QWEN_API_KEY` 仅为占位，可由获授权的运行环境注入，或写入已被 Git 忽略且权限为 `0600` 的本地 `.env`：

```text
MINISO_LLM_PROVIDER=qwen
QWEN_API_KEY=<运行时安全注入>
QWEN_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
QWEN_MODEL=qwen3.7-plus
QWEN_ENABLE_THINKING=false
```

远程模型只改写或增强叙述，不改候选的确定性数值、八维权重、阈值和严重风险闸口。配置了 `qwen` 但缺少 Key 时，`configured_provider` 保持 `qwen`，`effective_provider` 明确为 `offline`；首个远程请求失败后也会显式熔断并降级为 `offline`，当前流程继续使用确定性结果。`GET /api/health` 可核验配置 provider 与实际 provider，降级事件写入脱敏 trace，不记录 Key、完整提示词或上游响应正文。

本地 `.env` 只用于当前机器运行，必须保持未跟踪且不得进入源码包、MANIFEST、ZIP、日志或截图；交付物只包含无真实值的 [`.env.example`](.env.example)。

MiniMax 仍作为兼容 provider 保留，已有调用方可继续使用 `MINISO_LLM_PROVIDER=minimax` 与现有 `MINIMAX_*` 变量；新接入和在线演示不以 MiniMax 为主路径。

## 接入经许可的公开评论

数据连接器只接受调用方明确提供的 JSON/JSONL URL。运行前必须确认网站条款、抓取许可、个人信息处理和研究用途：

```bash
PYTHONPATH=backend .venv/bin/python \
  -m miniso_studio.infrastructure.data.retail_reviews \
  --source-url 'https://example.org/authorized-reviews.jsonl' \
  --brand MINISO --max-reviews 800
```

处理后数据写入 `data/processed/`，并优先于合成样本加载。连接器不会证明数据代表企业全量消费者，也不会自动获得商用许可。企业内部数据应通过独立的权限、脱敏和审计连接器接入。

## 架构与目录

- [`backend/miniso_studio/starter/`](backend/miniso_studio/starter/)：CLI、FastAPI、SSE、HITL 入口。
- [`backend/miniso_studio/application/`](backend/miniso_studio/application/)：状态图、Agent、评分、评测与报告。
- [`backend/miniso_studio/infrastructure/`](backend/miniso_studio/infrastructure/)：数据、ABSA、检索、模型网关、trace、媒体适配。
- [`backend/miniso_studio/common/`](backend/miniso_studio/common/)：配置、模型、引用与工具注册表。
- [`frontend/`](frontend/)：动态经营决策工作台。
- [`data/`](data/)：合成样本生成器、processed 数据入口与边界说明。
- [`backend/tests/`](backend/tests/)：单元、契约、并发、迁移和材料测试。
- [`docs/`](docs/)：方法论、报名文案、补充材料、来源与迁移说明。
- [`skills/`](skills/)：兴趣消费 VOC 分析 SOP。

核心状态流：

```text
九项输入 + Evidence -> VOC 洞察 -> 趋势雷达 -> 三路径动态候选
                    -> 用户镜像 -> 商品专家 -> 八维评审 -> HITL -> 提案
                                                   +-> 不达标时带条件回到候选迭代
```

## 测试与审计

开发依赖见 [`requirements-dev.txt`](requirements-dev.txt)，测试集位于 [`backend/tests/`](backend/tests/)，前端入口为 [`frontend/app.js`](frontend/app.js)，提交前检查脚本为 [`scripts/pre_pr_check.py`](scripts/pre_pr_check.py)。

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
node --check frontend/app.js
.venv/bin/python -m compileall -q backend scripts run.py
.venv/bin/python scripts/pre_pr_check.py
```

测试覆盖固定种子数据与中文/英文 ABSA、九项输入规范化、动态候选与报告传播、三候选与八维权重、工具真实调用、严重风险保护、候选隔离、稳定排序、Qwen 网关和显式降级、API/SSE、并发运行、HITL checkpoint、报告数据边界和报名文字数。测试命令是否通过以当前工作区的实际输出为准，本文不替代验收记录。

## 资料、打包与合规

- [`docs/报名提交材料.md`](docs/报名提交材料.md)：满足表单字符限制的 Part 1 / Part 2。
- [`docs/开题报告补充材料.md`](docs/开题报告补充材料.md)：固定 17 页附件内容源。
- [`docs/methodology_whitepaper.md`](docs/methodology_whitepaper.md)：三路径、工具、评分、HITL 和校准方法。
- [`docs/ai_vs_experience.md`](docs/ai_vs_experience.md)：同题、同数据、同预算的影子试点设计，不预设 AI 胜出。
- [`docs/references.md`](docs/references.md)：2026 年官方经营资料与 Agent 一手资料。
- [`docs/迁移说明.md`](docs/迁移说明.md)：固定输入 v1 到动态输入 v2 的兼容、破坏性变化、安全与降级说明。
- [`deliverables/提交清单_v2.md`](deliverables/提交清单_v2.md)：逐项执行并留证的交付清单。

源码包由 [`scripts/package_submission_v1.py`](scripts/package_submission_v1.py) 使用正向 allowlist 生成，调用方必须传入全新的输出目录：

```bash
.venv/bin/python scripts/package_submission_v1.py \
  --output-dir outputs-trend2sku-v3
```

脚本文件名为兼容既有命令而保留，内部包名已升级为 `miniso-ai-product-studio-v2`。打包器拒绝覆盖已有同名目录、ZIP 或校验文件，并排除运行产物、缓存、旧截图/报告、密钥文件和 [`docs/superpowers/`](docs/superpowers/)。

基线仓库在 2026-07-19 核验时没有检测到许可证文件，GitHub API 返回 `license: null`。公开可读不等于获得开源授权；比赛上传、公开仓库或第三方分发前，必须先完成 [`docs/迁移说明.md`](docs/迁移说明.md) 中的授权或独立重写确认。
