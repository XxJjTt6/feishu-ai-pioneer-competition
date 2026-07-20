# Trend2SKU Qwen 动态决策工作台

这套入口将工作台的核心生成链路交给 `qwen3.7-plus`，不是在浏览器中拼接固定候选或固定决策简报。

## 在线生成范围

- 三条互相区分的候选路径与商品名称
- 每个候选的价值主张、功能和差异点
- 合成用户画像、三轮访谈、异议和必须修正项
- 商品化判断、风险描述和缓解动作
- 三个候选共 24 条八维评分依据
- 组合理由、推进条件和完整 PRFAQ 提案

## 本地确定性护栏

- 候选 ID 固定为 `C-VOC`、`C-TREND`、`C-WHITESPACE`，避免跨模块串位
- 八维数值、权重、总分和排序由本地评分器计算
- 模型引用的证据 ID 必须通过本轮证据白名单
- 模型提出的风险属于待验证假设，最高按中风险进入展示，不能触发质量或 IP 阻断
- 质量与 IP 的高风险闸口只接受本地规则和确定性商品评估结果
- 远程调用失败时会明确标记降级，不会伪装成 Qwen 成功结果

## 启动

1. 参考 [环境变量模板](.env.example) 配置本机已被 Git 忽略的 `.env`。
2. 安装 [运行依赖](requirements.txt) 和 [开发依赖](requirements-dev.txt)。
3. 启动动态入口：

```bash
python run_qwen_live.py
```

4. 打开 `http://127.0.0.1:8767/`。

API Key 只存在服务端环境变量中，不会进入前端、运行结果、追踪文件或 GitHub Pages 产物。

## 关键实现

- [Qwen JSON 客户端](backend/miniso_studio/infrastructure/llm/structured_qwen_dynamic.py)
- [动态决策引擎](backend/miniso_studio/application/llm_decision_dynamic.py)
- [多角色 Agent 适配](backend/miniso_studio/application/agents/llm_agents_dynamic.py)
- [Qwen 与确定性评分工作流](backend/miniso_studio/application/graph/pipeline_llm_dynamic.py)
- [动态报告](backend/miniso_studio/application/reporting_llm_dynamic.py)
- [服务端入口](backend/miniso_studio/starter/live_app_dynamic.py)
- [工作台页面](frontend/index-qwen-live.html)
- [工作台交互](frontend/app-qwen-live.js)
- [工作台样式](frontend/styles-qwen-live.css)

## 验证

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_qwen_dynamic_decision.py \
  backend/tests/test_qwen_live_app.py -q

node --check frontend/app-qwen-live.js
```

测试覆盖两次结构化 Qwen 调用、动态内容映射、确定性风险护栏、API Key 脱敏、候选切换、访谈与商品化详情、报告交互，以及 `375`、`390`、`1121`、`1440` 四种浏览器宽度。

## 部署边界

GitHub Pages 只能托管静态前端，不能安全保存阿里云 API Key，也不能运行 Python 工作流。公开演示必须让 Pages 连接独立的 HTTPS 后端；不得把 Key 写入 JavaScript、仓库 Secret 以外的位置或公共 CORS 代理。
