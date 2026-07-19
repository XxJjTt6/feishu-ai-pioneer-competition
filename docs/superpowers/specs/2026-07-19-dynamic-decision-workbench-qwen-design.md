# Trend2SKU 动态决策工作台与 Qwen3.7 Plus 接入设计

## 目标

把现有固定演示页升级为用户输入真正驱动候选生成、评分、验证和报告的经营工作台，并把所有远程 LLM 叙述能力统一接入阿里云百炼 Coding Plan 的 OpenAI 兼容端点与 `qwen3.7-plus` 模型。确定性评分、风险闸口和证据引用继续由本地代码控制，LLM 不得改写数值事实。

## 版本与安全边界

- 原版本 `trend2sku-miniso-agent-v1` 保持不变，全部工作落在独立的 `trend2sku-miniso-agent-v2`。
- Coding Plan Key 只保存在根目录 `.env`，文件权限设为仅当前用户可读写。
- `.env`、密钥、请求头、模型全文和本机路径不得进入 Git、trace、日志、截图、MANIFEST 或 ZIP。
- 提交包只包含 `.env.example`；在线配置缺失或远程调用失败时，系统显式降级为 `offline`。
- Coding Plan OpenAI Base URL 为 `https://coding.dashscope.aliyuncs.com/v1`，模型 ID 固定为 `qwen3.7-plus`，协议端点为 `/chat/completions`。

## 决策输入

新增稳定的 `DecisionInput` 数据契约：

| 字段 | 约束 | 用途 |
|---|---|---|
| `brief` | 必填，1-500 字符 | 用户的核心决策任务 |
| `product_category` | 受控枚举加 `other` | 决定商品形态与概念词汇 |
| `custom_category` | 选择 `other` 时必填 | 支持未预设的兴趣消费品类 |
| `target_segment` | 受控枚举 | 改变用户镜像与价值主张 |
| `target_market` | 受控枚举 | 改变本地化与合规关注点 |
| `price_band` | 受控枚举 | 改变材料、组合和毛利假设 |
| `ip_strategy` | 受控枚举 | 改变原创/IP 授权风险 |
| `objectives` | 1-4 个受控目标 | 决定候选优化优先级 |
| `constraints` | 可选，最多 300 字符 | 记录材料、成本、交期与渠道约束 |

前端首次打开时不提供任何固定答案，`brief` 为空，仅显示占位提示。必填字段不完整时运行按钮保持禁用并给出字段级提示。

## 动态候选

- 保留 `C-VOC`、`C-TREND`、`C-WHITESPACE` 三条可解释路径和稳定 ID。
- 新的候选工厂按品类配置描述商品名词、基础形态、功能模块和常见风险，再结合人群、市场、价格带、IP 策略、目标和约束形成候选。
- 不同 `DecisionInput` 必须生成不同的候选名称、卖点、功能、验证问题和报告摘要。
- 用户输入不能直接增加评分。输入先改变候选方案和风险暴露，再由现有八维量表、证据和严重风险规则评分，避免关键词刷分。
- API 视图回传完整但已规范化的 `decision_input` 快照，前端显示本轮实际参数并按 `run_id/thread_id` 绑定。

## 前端交互

- 决策输入区使用 select、多选 checkbox、价格带菜单、自由文本和清空图标按钮；不使用伪按钮。
- “运行 Agent”构造结构化请求并通过 SSE 发送全部参数，运行期间禁用所有会改变当前请求的控件。
- 候选排行由 API 数据生成，切换时联动评分、概念、用户验证和商品风险。
- 证据按钮只在对应 evidence ID 可解析时启用。
- 完整报告与开题摘要改为页面内报告对话框，安全加载 Markdown 纯文本；提供真实的 Markdown 下载按钮。
- 新增结果 JSON 下载和“使用当前条件再次运行”；每轮创建新的 thread/run，不覆盖旧运行。
- 空状态、加载、错误、远程降级和完成状态均有明确反馈。

## Qwen 网关

- `Settings.llm_provider` 增加 `qwen`，新增 `QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`、`QWEN_ENABLE_THINKING`。
- 新建 `QwenClient`，调用 OpenAI 兼容 `/chat/completions`，Authorization 使用 Bearer Key。
- 非流式请求显式发送 `enable_thinking=false`，避免模型思考模式与非流式接口冲突。
- `LLMGateway` 使用通用 remote client，不再把远程逻辑写死为 MiniMax；保留 MiniMax 兼容路径，但 v2 的实际 `.env` 只启用 Qwen。
- API health、运行视图、报告和 trace 显示 `configured_provider=qwen`、实际 provider 和 `qwen3.7-plus`，但绝不显示 Key。

## 错误处理

- 无效枚举、空简报、过长约束、`other` 缺少自定义品类时返回 422。
- Qwen HTTP、超时、解析或空响应错误只记录安全摘要与请求 ID，不记录请求头、Key、完整响应或用户正文。
- 首次远程失败后该次运行切换到 offline，后续节点不重复请求故障端点。
- 报告加载失败保留当前决策视图并允许重试，不清空已生成结果。

## 测试与验收

- 测试先行覆盖 `DecisionInput` 校验、URL 编码、输入快照、Qwen 请求体、密钥不泄露和 provider 降级。
- 两组不同输入必须产生不同候选名称、特征、验证文本和报告文本。
- 浏览器验证空白简报、按钮启用条件、清空、再次运行、候选联动、报告对话框与下载。
- 375、390、1121、1440 宽度无页面级溢出，移动端所有状态可见。
- 原有 121 项测试继续通过；最终从无密钥 ZIP 解压后再次运行全量测试、CLI、API、SSE、MANIFEST 和隐私扫描。
- 最终服务必须报告实际使用 `qwen3.7-plus`；如果 Coding Plan 端点拒绝自定义后端调用，交付中明确记录真实错误并保持 offline 可运行，不伪造在线成功。
