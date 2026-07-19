# Trend2SKU 参考资料与事实索引

本清单按“企业与赛题一手资料、Agent 工程一手资料、迁移授权核验”分组。访问日统一为 **2026-07-19**。经营数据保留发布日期、报告期和审计口径；技术文章只支持相应的设计原则，不把特定团队的经验或效果数字外推为本项目收益。

## 一、MINISO 与赛题一手资料

### F1｜MINISO Group 2026 年 3 月季度业绩

- **机构**：MINISO Group Holding Limited（Investor Relations）
- **标题**：*MINISO Group Announces March Quarter 2026 Unaudited Financial Results*
- **发布日期**：2026-05-26
- **报告期**：截至 2026-03-31 的季度，**未经审计**
- **URL**：https://ir.miniso.com/2026-05-26-MINISO-Group-Announces-March-Quarter-2026-Unaudited-Financial-Results
- **访问日**：2026-07-19
- **支持事实**：集团收入人民币 56.884 亿元、同比增长 28.5%；MINISO 品牌收入同比增长 26.6%；中国内地和海外收入分别同比增长 29.6% 与 21.9%。截至 2026-03-31，集团门店 8,565 家，其中 MINISO 门店 8,210 家，内地 4,593 家、海外 3,617 家；过去十二个月新增 MINISO 门店约 56% 位于海外。授权费用同比增长 42.0%，约占收入 2.6%。
- **使用限制**：授权费用是费用口径，不是 IP 收入、IP 需求或单品收益；管理层关于 2026 年下半年全球化、IP 与产品组合优化的表述属于前瞻性陈述。

### F2｜MINISO Group 2025 年年报 / Form 20-F

- **机构**：MINISO Group Holding Limited
- **标题**：*Annual Report 2025*（Form 20-F）
- **发布日期**：2026-04-24
- **报告期**：截至 2025-12-31 的年度
- **URL**：https://ir.miniso.com/image/Annual+Report+2025+US.pdf
- **访问日**：2026-07-19
- **支持事实**：2025 年集团收入人民币 214.438 亿元，同比增长 26.2%；集团 GMV 约人民币 371 亿元；毛利率 45.0%；海外收入占 MINISO 品牌收入 44.2%；MINISO 平均每月推出约 1,600 个 SKU。截至 2025-12-31，MINISO 门店 8,151 家，其中内地 4,568 家、海外 3,583 家。
- **组织与系统事实**：截至 2025-12-31，超过 300 名产品经理、超过 300 名内部设计师、约 2,000 家供应商；产品开发中已使用 Smart Merchandise Selection Assistant，并建有产品生命周期管理系统（PLM）。
- **使用限制**：这些事实说明企业已有数字化选品与 PLM 基础。本方案定位为跨数据源、候选验证、统一评分与审计的决策连接层，不声称企业“没有数字化”。集团毛利率不能直接当作某个候选 SKU 的毛利目标。

### F3｜2026 AI 先锋未来人才大赛：名创优品命题

- **机构**：飞书活动平台 / 赛事主办方
- **标题**：名创优品「AI 驱动的产品开发智能决策引擎」命题详情
- **发布日期**：页面未标明独立发布日期
- **适用期**：2026 年赛事命题
- **URL**：https://activity.feishu.cn/future-talent?detail=mingchuangyoupin
- **访问日**：2026-07-19
- **支持事实**：命题要求围绕“趋势感知 → 产品创意 → 上市验证”探索端到端智能决策引擎，并回应趋势变化快、选品判断复杂、上市反馈慢三类挑战。
- **使用限制**：命题中的愿景不是已实现的业务收益；本项目将其转化为可验证的工程契约和试点指标。

## 二、Agent 工程一手资料

### A1｜OpenAI Agent 构建指南

- **机构**：OpenAI
- **标题**：*A Practical Guide to Building Agents*
- **发布日期**：2025-04-07（PDF 元数据创建日期）
- **URL**：https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
- **访问日**：2026-07-19
- **支持原则**：Agent 适合需要多步决策、工具使用与护栏的工作流；应先验证单 Agent 或较简单编排是否足够，再按复杂度增加多 Agent；工具、指令和 guardrail 是基础设计要素。
- **本项目映射**：六类职责通过受控状态图协作，数值评分与硬性风险规则留在确定性代码中。

### A2｜OpenAI Function Calling 官方文档

- **机构**：OpenAI
- **标题**：*Function calling | OpenAI API*
- **发布日期**：持续更新页面，未标明固定发布日期
- **URL**：https://platform.openai.com/docs/guides/function-calling
- **访问日**：2026-07-19
- **支持原则**：通过结构化工具定义把模型与外部数据或动作连接，并对工具参数与输出进行校验。
- **本项目映射**：工具注册表区分只读能力，Agent 实际调用证据检索、趋势获取、候选生成、商品评估和组合评分工具；离线 fallback 也写入 trace。

### A3｜OpenAI Agents SDK Tracing 官方文档

- **机构**：OpenAI
- **标题**：*Tracing | OpenAI Agents SDK*
- **发布日期**：持续更新页面，未标明固定发布日期
- **URL**：https://openai.github.io/openai-agents-python/tracing/
- **访问日**：2026-07-19
- **支持原则**：Agent、生成、函数工具、护栏与交接可作为 trace/span 记录；敏感输入输出应谨慎采集或关闭。
- **本项目映射**：本项目使用自有轻量 JSONL trace，记录节点、工具名、状态、降级标志及脱敏摘要，不记录完整密钥或敏感载荷；并不声称使用了 OpenAI Agents SDK 本身。

### A4｜Anthropic Agent 评测指南

- **机构**：Anthropic
- **标题**：*Demystifying evals for AI agents*
- **发布日期**：2026-01-09
- **URL**：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **访问日**：2026-07-19
- **支持原则**：Agent 评测应区分任务、trial、grader、trace 与最终环境 outcome；多轮和工具调用增加误差传播，因此既要评轨迹，也要评结果，并通过多次试验与人工校准提高可信度。
- **本项目映射**：离线回归测试证明工程契约，真实业务有效性必须由影子试点、实物小样和上市后 outcome 另行验证。

### A5｜Anthropic 多 Agent 研究系统

- **机构**：Anthropic
- **标题**：*How we built our multi-agent research system*
- **发布日期**：2025-06-13
- **URL**：https://www.anthropic.com/engineering/multi-agent-research-system
- **访问日**：2026-07-19
- **支持原则**：多 Agent 可以并行探索复杂问题，但会增加协调、成本和评测难度；文章中的研究效果只适用于其特定系统与任务。
- **本项目映射**：三条候选路径并行保留差异，之后在同一规则量表中比较；不引用该文章的特定增益作为本项目收益。

### A6｜Anthropic Agent 工具设计

- **机构**：Anthropic
- **标题**：*Writing effective tools for AI agents—using AI agents*
- **发布日期**：2025-09-11
- **URL**：https://www.anthropic.com/engineering/writing-tools-for-agents
- **访问日**：2026-07-19
- **支持原则**：工具接口应清晰、上下文高信号、返回值易于消费，并通过评测迭代，而非把底层 API 机械暴露给 Agent。
- **本项目映射**：工具输入采用结构化模型，输出摘要进入 trace，错误时使用可见 fallback，数值评分不会由自由文本直接改写。

## 三、迁移与授权核验资料

### L1｜基线仓库元数据与树对象

- **机构**：GitHub / Git 仓库对象
- **仓库**：https://github.com/bcefghj/anker-ai-product-studio
- **基线提交**：`4e39aa12d8c67ea771168c492c106f5da38fbcee`
- **核验日期**：2026-07-19
- **核验结果**：GitHub REST API 返回 `license: null`；基线提交树中未发现 `LICENSE` 或同名许可证文件。
- **使用限制**：公开可读不等于获得开源许可。提交、公开仓库或向第三方分发迁移版本前，必须取得原权利人的明确授权，或完成并留存可证明的独立重写证据。详细阻断条件见 `docs/迁移说明.md`。

## 四、引用与数值使用规则

1. “官方事实”只引用 F1–F3，并同时显示报告期或发布日期；公司新闻稿数据按公司披露处理。
2. `[离线演示]` 只描述可复现工程运行，不代表企业内部数据、真实消费者、销量、毛利、爆款概率、命中率或 ROI。
3. `[试点目标]` 必须先定义基线、样本、时间窗、口径和数据授权，再由企业方锁定目标值。
4. “最终业务结果”只定义测量方法，不在没有真实对照数据时预设提升幅度。
5. A1–A6 只支持工具、编排、trace、评测和人工复核的设计原则，不证明本项目已经产生商业效果。
