# Trend2SKU 爆款产品决策 Agent

> 名创优品「AI 驱动的产品开发智能决策引擎」命题原型：趋势感知 → 产品创意 → 上市验证。

## 先看数据边界

仓库自带数据是固定种子 `20260719` 生成的 **400 条合成离线演示评论**：MINISO 140 条，POP MART、DAISO、MUJI、Flying Tiger 各 65 条。它们不是企业内部数据，不是真实用户评论、销售、毛利或试购记录，也不代表任何品牌的实际表现。

所有候选总分都是统一规则量表的 `xx/100`，**不是爆款概率**；模拟访谈接受度与模拟 NPS **不是实测购买或真实用户研究**。2026 年官方经营数字只用于说明决策规模与约束，不能直接推导单品需求、销量或 ROI。公开或企业数据接入前必须确认来源条款、授权、隐私和保存期限。

## 项目能做什么

Trend2SKU 在一次可审计运行中：

1. 对兴趣消费评论执行确定性方面分析，形成机会与证据索引。
2. 读取带日期和 URL 的趋势信号，拆解可比品牌并识别白空间。
3. 沿 VOC 需求、趋势主题、竞品白空间三条路径生成至少三个候选 SKU。
4. 为每个候选分别进行离线用户镜像验证与商品风险评估，不按数组位置串线。
5. 按八维固定权重评分，稳定排序；严重 IP 或质量风险不得直接 `GO`。
6. 输出榜首提案、风险条件、引用索引与 JSONL trace；可选 HITL 在决策点等待人工批准。

六类能力分别是趋势雷达、用户镜像、创意工坊、商品专家、爆款评审和提案生成。Agent 会真实经过只读工具注册表；远程模型仅用于叙述增强，不控制数值评分和风险闸口。

## 快速开始

需要 Python 3.10+。下面以仓库根目录为当前目录：

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

CLI 会打印候选排名，并在 `docs/generated/` 中创建新的版本化 Markdown 报告；若同名旧文件存在，不会原地覆盖。每次运行的 trace 位于 `runs/<run_id>.jsonl`。

## 浏览器工作台与 API

```bash
PYTHONPATH=backend MINISO_LLM_PROVIDER=offline \
  .venv/bin/python -m uvicorn miniso_studio.starter.api:app \
  --host 127.0.0.1 --port 8767
```

浏览器打开 `http://127.0.0.1:8767`。健康检查与同步运行示例：

```bash
curl -s http://127.0.0.1:8767/api/health

curl -s -X POST http://127.0.0.1:8767/api/run \
  -H 'Content-Type: application/json' \
  -d '{"category":"interest_goods","brief":"生成春季礼赠候选组合"}'
```

`POST /api/run` 返回独立的 `run_id` 和 `thread_id`。报告接口 **必须显式传入该次返回的 `run_id`**，不能依赖“最后一次运行”：

```bash
RUN_ID="$(
  curl -s -X POST http://127.0.0.1:8767/api/run \
    -H 'Content-Type: application/json' \
    -d '{"brief":"生成可审计的礼赠候选组合"}' \
  | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])'
)"
curl -s "http://127.0.0.1:8767/api/report?run_id=${RUN_ID}&kind=full"
curl -s "http://127.0.0.1:8767/api/report?run_id=${RUN_ID}&kind=opening"
```

SSE 运行入口是 `GET /api/stream?brief=...`，依次发送 trace、result/error 和 done；并发运行各自持有独立 `run_id`。服务进程只缓存最近 20 次运行，生产接入应替换为有权限和留存策略的持久化存储。

## 人工复核

命令行启用 HITL：

```bash
PYTHONPATH=backend MINISO_LLM_PROVIDER=offline MINISO_HITL=true \
  .venv/bin/python -m miniso_studio.starter.cli run \
  --thread pilot-review-001

PYTHONPATH=backend .venv/bin/python -m miniso_studio.starter.cli resume \
  --thread pilot-review-001
```

API 使用 `POST /api/run` 传入 `{"hitl":true,"thread_id":"pilot-review-002"}`，再以 `POST /api/resume` 提交 `{"thread_id":"pilot-review-002","action":"approve"}`。同一 thread 的重复运行、并发恢复和重复消费 checkpoint 会返回冲突，而不是静默覆盖状态。

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

总分 `>=75` 建议 `GO`，`60–74.99` 建议 `CONDITIONAL_GO`，`<60` 建议 `NO_GO`。严重 IP 或质量风险会阻止直接 `GO`。权重、阈值和确定性输入需要在获得企业历史候选与真实上市 outcome 后重新校准。

## 在线叙述增强

离线模式不需要 API Key。需要在线叙述增强时，新建 `.env` 并设置：

```dotenv
MINISO_LLM_PROVIDER=minimax
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-M3
```

完整变量见 `.env.example`，实际密钥通过本地环境或密钥管理服务注入。密钥不得提交到 Git，也不得进入 trace。即使启用远程模型，八维分数、权重、阈值和严重风险规则仍由确定性代码负责。

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

```text
backend/miniso_studio/
  starter/          CLI、FastAPI、SSE、HITL 入口
  application/      状态图、Agent、评分、评测与报告
  infrastructure/   数据、ABSA、检索、模型网关、trace、媒体适配
  common/           配置、模型、引用与工具注册表
frontend/           经营决策工作台
data/               合成样本生成器、processed 数据入口与边界说明
backend/tests/      单元、契约、并发、迁移和材料测试
docs/               方法论、报名文案、补充材料、来源与迁移说明
skills/             兴趣消费 VOC 分析 SOP
```

核心状态流：

```text
Evidence → VOC 洞察 → 趋势雷达 → 三路径候选
         → 用户镜像 → 商品专家 → 八维评审 → HITL → 提案
                                      ↘ 不达标时带条件回到候选迭代
```

## 测试与审计

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/pre_pr_check.py
```

测试覆盖：固定种子数据与中文/英文 ABSA、三候选与八维权重、工具真实调用、严重风险保护、候选隔离、稳定排序、API/SSE、并发运行、HITL checkpoint、报告数据边界和报名文字数。

## 资料与合规

- `docs/报名提交材料.md`：满足表单字符限制的 Part 1 / Part 2。
- `docs/开题报告补充材料.md`：固定 17 页附件内容源。
- `docs/methodology_whitepaper.md`：三路径、工具、评分、HITL 和校准方法。
- `docs/ai_vs_experience.md`：同题、同数据、同预算的影子试点设计，不预设 AI 胜出。
- `docs/references.md`：2026 年官方经营资料与 Agent 一手资料。
- `docs/迁移说明.md`：基线、重写边界与许可证阻断确认。

基线仓库在 2026-07-19 核验时没有检测到许可证文件，GitHub API 返回 `license: null`。公开可读不等于获得开源授权；比赛上传、公开仓库或第三方分发前，必须先完成 `docs/迁移说明.md` 中的授权或独立重写确认。
