"use strict";

function configuredApiBase() {
  if (typeof window === "undefined" || typeof document === "undefined") return "";
  const queryValue = new URLSearchParams(window.location.search).get("api");
  const metaValue = document.querySelector('meta[name="trend2sku-api-base"]')?.content || "";
  const candidate = String(queryValue || metaValue).trim();
  if (!candidate) return "";
  try {
    const parsed = new URL(candidate, window.location.href);
    if (!new Set(["http:", "https:"]).has(parsed.protocol)) return "";
    return parsed.href.replace(/\/$/, "");
  } catch (_error) {
    return "";
  }
}

const API_BASE = configuredApiBase();

function configuredAccessToken() {
  if (typeof window === "undefined") return "";
  const value = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("access") || "";
  const token = String(value).trim();
  return /^[A-Za-z0-9_-]{16,128}$/.test(token) ? token : "";
}

const ACCESS_TOKEN = configuredAccessToken();

function accessHeaders(token, initial = {}) {
  const headers = { ...initial };
  if (token) headers["X-Trend2SKU-Access"] = String(token);
  return headers;
}

function apiUrl(path) {
  const normalized = String(path || "").replace(/^\/+/, "");
  return API_BASE ? `${API_BASE}/${normalized}` : normalized;
}

function requireStrictGeneration(raw) {
  const generation = asObject(raw);
  const completed = asArray(generation.completed_tasks).map((value) => String(value));
  const required = asArray(generation.required_tasks).map((value) => String(value));
  const complete = generation.mode === "qwen_strict_dynamic"
    && generation.qwen_complete === true
    && generation.model === "qwen3.7-plus"
    && generation.fallback_used === false
    && required.length === 2
    && required.every((task) => completed.includes(task));
  if (!complete) throw new TypeError("qwen_generation_incomplete");
  return generation;
}

const STAGE_ORDER = [
  "insight",
  "trend_radar",
  "ideation",
  "user_mirror",
  "merchandise_expert",
  "hit_judge",
  "proposal",
];

const STAGE_LABELS = {
  insight: "需求洞察",
  trend_radar: "趋势雷达",
  ideation: "创意工坊",
  user_mirror: "用户镜像",
  merchandise_expert: "商品专家",
  hit_judge: "爆款评审",
  proposal: "提案生成",
};

const VERDICT_LABELS = {
  GO: "建议推进",
  CONDITIONAL_GO: "条件推进",
  NO_GO: "建议暂缓",
  PENDING: "待评审",
};

const PATH_LABELS = {
  trend_driven: "趋势与 IP",
  voc_driven: "用户需求",
  whitespace_driven: "竞品白空间",
};

const INTERVIEW_VERDICT_LABELS = {
  would_buy: "愿意购买",
  maybe: "考虑购买",
  would_not_buy: "暂不购买",
  neutral: "待验证",
};

const RISK_AREA_LABELS = {
  quality: "质量",
  supply_chain: "供应链",
  gross_margin: "毛利",
  ip: "IP 权利",
  ip_authorization: "IP 授权",
  ip_compliance: "IP 合规",
  compliance: "合规",
  regional_compliance: "区域合规",
  market: "市场",
  technical: "技术",
  localization: "本地化",
};

const ASSESSMENT_LABELS = {
  green: "可推进",
  yellow: "需验证",
  red: "有阻断风险",
};

const METRIC_LABELS = {
  groundedness: "证据覆盖度",
  faithfulness: "引用一致性",
  citation_hit_rate: "引用命中率",
  opportunity_coverage: "机会覆盖率",
  persona_fidelity: "用户镜像可追溯性",
  explainability: "可解释性",
  overall: "综合质量",
};

function interviewVerdictLabel(value) {
  return INTERVIEW_VERDICT_LABELS[String(value || "")] || "待验证";
}

function riskAreaLabel(value) {
  const key = String(value || "");
  return RISK_AREA_LABELS[key] || key || "商品风险";
}

function assessmentLabel(value) {
  return ASSESSMENT_LABELS[String(value || "")] || "待校准";
}

function metricLabel(value) {
  const key = String(value || "");
  return METRIC_LABELS[key] || key.replaceAll("_", " ");
}

function runtimeTraceMessage(rawTrace) {
  const trace = rawTrace && typeof rawTrace === "object" ? rawTrace : {};
  const node = String(trace.node || "");
  const kind = String(trace.kind || "");
  if (Object.hasOwn(STAGE_LABELS, node) && kind === "start") return `${STAGE_LABELS[node]} · 运行中`;
  if (Object.hasOwn(STAGE_LABELS, node) && kind === "end") return `${STAGE_LABELS[node]} · 已完成`;
  if (kind === "llm_call" && trace.task === "strategy") return "Qwen 已生成动态候选与合成验证";
  if (kind === "llm_call" && trace.task === "decision") return "Qwen 已完成评分解释与提案";
  if (kind === "provider_fallback") return "远程模型不可用，本轮已启用确定性降级";
  return "";
}

function canRunDecision(validation, running, serviceReady) {
  return Boolean(validation?.valid && !running && serviceReady);
}

const SSE_MESSAGE_TYPES = new Set(["heartbeat", "trace", "result", "error", "done"]);

const DECISION_OPTIONS = {
  product_category: new Set([
    "plush",
    "fragrance_accessory",
    "stationery",
    "home_storage",
    "beauty_tool",
    "digital_accessory",
    "other",
  ]),
  target_segment: new Set(["student", "young_professional", "ip_fan", "gift", "family", "collector"]),
  target_market: new Set(["china", "southeast_asia", "japan_korea", "europe_america", "middle_east", "global"]),
  price_band: new Set(["entry", "mid", "premium"]),
  ip_strategy: new Set(["original", "licensed", "none", "evaluate"]),
  objectives: new Set(["emotional", "social", "margin", "supply_chain", "localization"]),
};

const DECISION_LABELS = {
  product_category: {
    plush: "毛绒",
    fragrance_accessory: "香氛配饰",
    stationery: "文创文具",
    home_storage: "家居收纳",
    beauty_tool: "美妆工具",
    digital_accessory: "数码配件",
    other: "其他",
  },
  target_segment: {
    student: "学生",
    young_professional: "年轻职场人",
    ip_fan: "IP 粉丝",
    gift: "礼赠人群",
    family: "亲子家庭",
    collector: "收藏爱好者",
  },
  target_market: {
    china: "中国",
    southeast_asia: "东南亚",
    japan_korea: "日韩",
    europe_america: "欧美",
    middle_east: "中东",
    global: "全球",
  },
  price_band: { entry: "入门", mid: "中端", premium: "高端" },
  ip_strategy: { original: "原创 IP", licensed: "授权 IP", none: "无 IP", evaluate: "IP 待评估" },
  objectives: {
    emotional: "情绪价值",
    social: "社交传播",
    margin: "毛利空间",
    supply_chain: "供应链",
    localization: "本地化",
  },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeText(value, limit = 600) {
  const text = String(value ?? "").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
  const safeLimit = Math.max(1, Number.isFinite(Number(limit)) ? Math.floor(Number(limit)) : 600);
  return text.length > safeLimit ? `${text.slice(0, safeLimit)}…` : text;
}

function safeHttpUrl(value) {
  const raw = String(value ?? "").trim();
  if (raw.startsWith("demo://")) return null;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch (_error) {
    return null;
  }
}

function clampScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function namedControlValue(form, name) {
  const controls = form?.elements;
  const control = typeof controls?.namedItem === "function" ? controls.namedItem(name) : controls?.[name];
  if (!control) return "";
  if (typeof control.value === "string") return control.value;
  const selected = Array.from(control).find((item) => item?.checked);
  return typeof selected?.value === "string" ? selected.value : "";
}

function readDecisionInput(form) {
  const checkedObjectives = typeof form?.querySelectorAll === "function"
    ? form.querySelectorAll('[name="objectives"]:checked')
    : [];
  const productCategory = String(namedControlValue(form, "product_category")).trim();
  return {
    brief: String(namedControlValue(form, "brief")).trim(),
    product_category: productCategory,
    custom_category: productCategory === "other" ? String(namedControlValue(form, "custom_category")).trim() : "",
    target_segment: String(namedControlValue(form, "target_segment")).trim(),
    target_market: String(namedControlValue(form, "target_market")).trim(),
    price_band: String(namedControlValue(form, "price_band")).trim(),
    ip_strategy: String(namedControlValue(form, "ip_strategy")).trim(),
    objectives: Array.from(checkedObjectives, (item) => String(item?.value || "").trim()).filter(Boolean),
    constraints: String(namedControlValue(form, "constraints")).trim(),
  };
}

function validateDecisionInput(rawInput) {
  const input = asObject(rawInput);
  const errors = {};
  const brief = String(input.brief ?? "").trim();
  const customCategory = String(input.custom_category ?? "").trim();
  const constraints = String(input.constraints ?? "").trim();
  const objectives = asArray(input.objectives).map((item) => String(item));

  if (!brief) errors.brief = "请输入决策简报。";
  else if (brief.length > 500) errors.brief = "决策简报最多 500 字。";
  for (const field of ["product_category", "target_segment", "target_market", "price_band", "ip_strategy"]) {
    if (!DECISION_OPTIONS[field].has(String(input[field] ?? ""))) errors[field] = "请选择有效选项。";
  }
  if (input.product_category === "other" && !customCategory) errors.custom_category = "请填写自定义品类。";
  else if (customCategory.length > 40) errors.custom_category = "自定义品类最多 40 字。";
  if (objectives.length < 1 || objectives.length > 4 || objectives.some((item) => !DECISION_OPTIONS.objectives.has(item))) {
    errors.objectives = "请选择 1-4 项经营目标。";
  }
  if (constraints.length > 300) errors.constraints = "约束条件最多 300 字。";
  return { valid: Object.keys(errors).length === 0, errors };
}

function buildStreamUrl(input, threadId) {
  const source = asObject(input);
  const params = new URLSearchParams();
  for (const field of [
    "brief",
    "product_category",
    "custom_category",
    "target_segment",
    "target_market",
    "price_band",
    "ip_strategy",
  ]) params.append(field, String(source[field] ?? ""));
  for (const objective of asArray(source.objectives)) params.append("objectives", String(objective));
  params.append("constraints", String(source.constraints ?? ""));
  params.append("thread_id", String(threadId ?? ""));
  return `api/stream?${params.toString()}&hitl=false`;
}

async function createStreamTicket(input, threadId, fetchImpl = fetch) {
  const response = await fetchImpl(apiUrl("api/stream/ticket"), {
    method: "POST",
    headers: accessHeaders(ACCESS_TOKEN, {
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({ ...asObject(input), thread_id: threadId, hitl: false }),
  });
  if (!response.ok) throw new Error("stream_ticket");
  const payload = asObject(await response.json());
  requireContract(payload.thread_id === threadId, "SSE 票据 thread_id 不一致");
  requireContract(
    /^api\/stream\?ticket=[a-f0-9]{32}$/.test(String(payload.stream_url || "")),
    "SSE 票据 URL 不符合契约",
  );
  return payload;
}

async function pollRunResult(threadId, fetchImpl = fetch, options = {}) {
  const selectedThreadId = requireIdentifier(threadId, "结果轮询 thread_id", 64);
  const settings = asObject(options);
  const maxAttempts = Number.isInteger(settings.maxAttempts)
    ? Math.min(Math.max(settings.maxAttempts, 1), 300)
    : 90;
  const intervalMs = Number.isFinite(settings.intervalMs)
    ? Math.min(Math.max(settings.intervalMs, 0), 10000)
    : 1500;
  const sleepImpl = typeof settings.sleepImpl === "function"
    ? settings.sleepImpl
    : (delay) => new Promise((resolve) => setTimeout(resolve, delay));
  const accessToken = String(settings.accessToken ?? ACCESS_TOKEN);
  const url = apiUrl(`api/result?thread_id=${encodeURIComponent(selectedThreadId)}`);

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let response;
    try {
      response = await fetchImpl(url, {
        cache: "no-store",
        headers: accessHeaders(accessToken, { Accept: "application/json" }),
      });
    } catch (_error) {
      if (attempt + 1 >= maxAttempts) throw new Error("result_poll_unavailable");
      await sleepImpl(intervalMs);
      continue;
    }

    if (response.status === 200) {
      const view = asObject(await response.json());
      requireContract(view.thread_id === selectedThreadId, "轮询结果 thread_id 不一致");
      return view;
    }
    if (response.status !== 202) {
      if (new Set([429, 502, 503, 504]).has(response.status) && attempt + 1 < maxAttempts) {
        await sleepImpl(intervalMs);
        continue;
      }
      throw new Error("result_poll_failed");
    }
    if (attempt + 1 < maxAttempts) await sleepImpl(intervalMs);
  }
  throw new Error("result_poll_timeout");
}

function decisionInputSummary(rawInput) {
  const input = asObject(rawInput);
  const category = input.product_category === "other"
    ? input.custom_category
    : DECISION_LABELS.product_category[input.product_category];
  const objectives = asArray(input.objectives)
    .map((value) => DECISION_LABELS.objectives[value] || value)
    .join("、");
  return [
    `本轮：${safeText(input.brief, 80)}`,
    safeText(category, 40),
    DECISION_LABELS.target_segment[input.target_segment] || input.target_segment,
    DECISION_LABELS.target_market[input.target_market] || input.target_market,
    DECISION_LABELS.price_band[input.price_band] || input.price_band,
    DECISION_LABELS.ip_strategy[input.ip_strategy] || input.ip_strategy,
    `目标 ${objectives}`,
    `约束 ${safeText(input.constraints || "无额外约束", 80)}`,
  ].join(" · ");
}

function safeDownloadId(value) {
  const normalized = String(value ?? "").replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return normalized.slice(0, 80) || "run";
}

function requireContract(condition, message) {
  if (!condition) throw new TypeError(message);
}

function requireIdentifier(value, label, limit = 128) {
  const identifier = String(value ?? "");
  requireContract(
    identifier.length > 0 && identifier.length <= limit && /^[A-Za-z0-9_-]+$/.test(identifier),
    `${label} 不符合契约`,
  );
  return identifier;
}

function normalizeView(raw) {
  const source = asObject(raw);
  const candidates = asArray(source.candidate_skus).filter((item) => item && typeof item === "object");
  const scorecards = asArray(source.scorecards).filter((item) => item && typeof item === "object");
  const decision = asObject(source.portfolio_decision);
  const winnerId = safeText(decision.winner_id || asObject(source.winner_scorecard).concept_id, 80);
  const evidenceIndex = asObject(source.evidence_index);
  return {
    ...source,
    candidate_skus: candidates,
    scorecards,
    winner_scorecard: asObject(source.winner_scorecard),
    portfolio_decision: decision,
    trend_signals: asArray(source.trend_signals),
    consumer_insights: asObject(source.consumer_insights),
    launch_validation: asObject(source.launch_validation),
    quality_audit: asObject(source.quality_audit),
    evidence_index: evidenceIndex,
    audit: asObject(source.audit),
    data_provenance: asObject(source.data_provenance),
    generation_provenance: asObject(source.generation_provenance),
    decision_input: asObject(source.decision_input),
    winner_id: winnerId,
  };
}

function validateViewContract(raw, expected = {}) {
  requireContract(raw && typeof raw === "object" && !Array.isArray(raw), "运行视图必须是对象");
  const view = normalizeView(raw);
  requireContract(view.schema_version === "1.0", "运行视图版本不受支持");
  requireContract(view.product === "Trend2SKU", "运行视图产品标识不匹配");
  const runId = requireIdentifier(view.run_id, "run_id");
  const threadId = requireIdentifier(view.thread_id, "thread_id", 64);
  if (expected.runId) requireContract(runId === expected.runId, "运行视图 run_id 与 SSE 不一致");
  if (expected.threadId) requireContract(threadId === expected.threadId, "运行视图 thread_id 与 SSE 不一致");
  requireContract(view.status === "completed" && view.awaiting_human === false, "前端只接受已关闭 HITL 的完整结果");
  requireStrictGeneration(view.generation_provenance);
  requireContract(validateDecisionInput(view.decision_input).valid, "运行视图缺少有效的决策输入快照");

  requireContract(view.candidate_skus.length >= 3, "运行视图至少需要三个候选 SKU");
  const candidateIds = view.candidate_skus.map((candidate) => {
    requireContract(candidate && typeof candidate === "object", "候选 SKU 结构无效");
    const id = requireIdentifier(candidate.id, "candidate.id", 80);
    requireContract(String(candidate.name ?? "").trim().length > 0, "候选 SKU 缺少名称");
    return id;
  });
  requireContract(new Set(candidateIds).size === candidateIds.length, "候选 SKU ID 必须唯一");

  const scorecardIds = view.scorecards.map((card) => {
    requireContract(card && typeof card === "object", "评分卡结构无效");
    const id = requireIdentifier(card.concept_id, "scorecard.concept_id", 80);
    const dimensions = asArray(card.dimensions);
    requireContract(dimensions.length === 8, "每个候选必须具备八维评分");
    const weightTotal = dimensions.reduce((sum, item) => sum + Number(item?.weight || 0), 0);
    requireContract(Math.abs(weightTotal - 1) < 0.0001, "八维评分权重必须合计 100%");
    requireContract(Number.isFinite(Number(card.total_score)), "评分卡缺少有效总分");
    return id;
  });
  requireContract(new Set(scorecardIds).size === scorecardIds.length, "评分卡 concept_id 必须唯一");
  requireContract(
    candidateIds.length === scorecardIds.length && candidateIds.every((id) => scorecardIds.includes(id)),
    "候选 SKU 与评分卡必须一一对应",
  );

  const winnerScorecard = asObject(view.winner_scorecard);
  const decision = asObject(view.portfolio_decision);
  const winnerId = requireIdentifier(decision.winner_id, "portfolio_decision.winner_id", 80);
  requireContract(candidateIds.includes(winnerId), "榜首必须来自候选组合");
  requireContract(winnerScorecard.concept_id === winnerId, "榜首评分卡与组合决策不一致");
  requireContract(["GO", "CONDITIONAL_GO", "NO_GO"].includes(decision.verdict), "组合建议不符合契约");

  const launchByCandidate = asObject(asObject(view.launch_validation).by_candidate);
  const qualityByCandidate = asObject(asObject(view.quality_audit).by_candidate);
  requireContract(candidateIds.every((id) => Object.hasOwn(launchByCandidate, id)), "候选缺少上市验证结果");
  requireContract(candidateIds.every((id) => Object.hasOwn(qualityByCandidate, id)), "候选缺少商品风险结果");
  requireContract(view.evidence_index && typeof view.evidence_index === "object", "运行视图缺少证据索引");
  requireContract(view.audit && typeof view.audit === "object", "运行视图缺少审计记录");
  return view;
}

function bindSseEnvelope(previous, rawMessage) {
  const message = asObject(rawMessage);
  requireContract(SSE_MESSAGE_TYPES.has(message.type), "未知 SSE 消息类型");
  const runId = requireIdentifier(message.run_id, "SSE run_id");
  const threadId = requireIdentifier(message.thread_id, "SSE thread_id", 64);
  const current = asObject(previous);
  if (current.runId) requireContract(current.runId === runId, "SSE run_id 在同一连接中发生变化");
  if (current.threadId) requireContract(current.threadId === threadId, "SSE thread_id 与请求不一致");
  return { runId: current.runId || runId, threadId: current.threadId || threadId };
}

function createClientThreadId() {
  const time = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 14) || "local";
  return `web-${time}-${random}`;
}

function selectCandidateModel(view, requestedId) {
  const normalized = normalizeView(view);
  const winnerId = normalized.winner_id;
  const winnerCandidate =
    normalized.candidate_skus.find((item) => item.id === winnerId) || normalized.candidate_skus[0] || {};
  const candidate =
    normalized.candidate_skus.find((item) => item.id === requestedId) || winnerCandidate;
  const scorecard =
    normalized.scorecards.find((item) => item.concept_id === candidate.id) ||
    (candidate.id === winnerId ? normalized.winner_scorecard : {}) ||
    {};
  return { view: normalized, candidate, scorecard, winnerCandidate };
}

function createRuntimeSnapshot() {
  return {
    phase: "idle",
    terminal: false,
    iteration: 1,
    stages: Object.fromEntries(STAGE_ORDER.map((stage) => [stage, "pending"])),
    warnings: [],
  };
}

function reduceRuntime(previous, action) {
  const current = previous || createRuntimeSnapshot();
  const next = {
    ...current,
    stages: { ...current.stages },
    warnings: [...current.warnings],
  };
  if (!action || typeof action !== "object") return next;

  if (action.type === "run_started") return { ...createRuntimeSnapshot(), phase: "running" };
  if (current.terminal) return next;
  if (action.type === "result_received") {
    for (const stage of STAGE_ORDER) {
      if (next.stages[stage] !== "error") next.stages[stage] = "done";
    }
    return { ...next, phase: "complete", terminal: true };
  }
  if (action.type === "run_error") return { ...next, phase: "error", terminal: true };
  if (action.type === "done") return { ...next, phase: "error", terminal: true };
  if (action.type === "disconnected") return { ...next, phase: "disconnected", terminal: true };
  if (action.type === "tool_warning") {
    next.phase = next.phase === "running" ? "partial" : next.phase;
    next.warnings.push(safeText(action.message || "工具已降级", 160));
    return next;
  }
  if (action.type !== "trace") return next;

  const event = asObject(action.event);
  const eventNode = safeText(event.node, 80);
  const stage = eventNode === "decision_review" ? "hit_judge" : eventNode;
  const kind = safeText(event.kind, 40);
  next.phase = next.phase === "running" || next.phase === "idle" ? "partial" : next.phase;
  if (!STAGE_ORDER.includes(stage)) return next;

  if (stage === "ideation" && kind === "start" && next.stages.ideation !== "pending") {
    next.iteration += 1;
    for (const later of STAGE_ORDER.slice(STAGE_ORDER.indexOf("ideation") + 1)) next.stages[later] = "pending";
  }
  if (kind === "start") next.stages[stage] = "active";
  if (kind === "end" && next.stages[stage] !== "error") next.stages[stage] = "done";
  if (kind === "error" || kind === "node_error") next.stages[stage] = "error";
  if (kind === "interrupt") next.stages[stage] = "waiting";
  return next;
}

const publicApi = {
  escapeHtml,
  safeText,
  safeHttpUrl,
  readDecisionInput,
  validateDecisionInput,
  buildStreamUrl,
  createStreamTicket,
  pollRunResult,
  decisionInputSummary,
  normalizeView,
  validateViewContract,
  bindSseEnvelope,
  createClientThreadId,
  selectCandidateModel,
  createRuntimeSnapshot,
  reduceRuntime,
  interviewVerdictLabel,
  riskAreaLabel,
  assessmentLabel,
  metricLabel,
  runtimeTraceMessage,
  canRunDecision,
  accessHeaders,
  requireStrictGeneration,
};

if (typeof module !== "undefined" && module.exports) module.exports = publicApi;

if (typeof document !== "undefined") {
  const dom = (id) => document.getElementById(id);
  const state = {
    runtime: createRuntimeSnapshot(),
    view: null,
    selectedId: null,
    eventSource: null,
    runToken: 0,
    running: false,
    reportKind: "full",
    reportMarkdown: "",
    reportToken: 0,
    formTouched: false,
    serviceReady: false,
  };

  function clearNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function appendText(parent, tag, text, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = safeText(text);
    parent.appendChild(element);
    return element;
  }

  function appendList(parent, items, className = "plain-list") {
    const list = document.createElement("ul");
    list.className = className;
    for (const item of asArray(items)) appendText(list, "li", item);
    parent.appendChild(list);
    return list;
  }

  function verdictLabel(value) {
    return VERDICT_LABELS[value] || "待评审";
  }

  function setRuntime(next, message) {
    state.runtime = next;
    document.body.dataset.phase = next.phase;
    const statusText = dom("runtimeStatusText");
    if (statusText && message) statusText.textContent = safeText(message, 180);
    for (const stage of STAGE_ORDER) {
      const item = document.querySelector(`[data-stage="${stage}"]`);
      if (!item) continue;
      const stageState = next.stages[stage] || "pending";
      item.dataset.state = stageState;
      const label = item.querySelector(".stage-state");
      if (label) {
        label.textContent = {
          pending: "待处理",
          active: "运行中",
          done: "已完成",
          waiting: "待审批",
          error: "已降级",
        }[stageState] || "待处理";
      }
    }
    const warning = dom("warningArea");
    if (warning) {
      warning.hidden = next.warnings.length === 0;
      warning.textContent = next.warnings.length ? safeText(next.warnings.at(-1), 180) : "";
    }
  }

  function evidenceButton(sourceId, label = "查看") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "evidence-button";
    button.textContent = label;
    const hasEvidence = Boolean(sourceId && state.view?.evidence_index?.[sourceId]);
    button.disabled = !hasEvidence;
    button.dataset.evidenceId = hasEvidence ? safeText(sourceId, 160) : "";
    if (hasEvidence) button.addEventListener("click", () => renderEvidence(sourceId));
    return button;
  }

  function renderWinner(view) {
    const target = dom("winnerContent");
    if (!target) return;
    clearNode(target);
    const selected = selectCandidateModel(view, view.winner_id);
    const winner = selected.winnerCandidate;
    const card = view.scorecards.find((item) => item.concept_id === winner.id) || view.winner_scorecard;
    if (!winner.id) {
      appendText(target, "p", "运行后生成组合榜首。", "empty-copy");
      return;
    }
    const layout = document.createElement("div");
    layout.className = "winner-layout";
    const copy = document.createElement("div");
    const winnerName = appendText(copy, "h4", winner.name);
    winnerName.dataset.testid = "winner-name";
    appendText(copy, "p", winner.one_liner, "muted-copy");
    const total = document.createElement("p");
    total.className = "winner-score";
    total.textContent = `${clampScore(card.total_score).toFixed(2)} / 100`;
    copy.appendChild(total);
    layout.appendChild(copy);
    target.appendChild(layout);
    const decision = view.portfolio_decision;
    appendText(target, "p", decision.rationale, "decision-rationale");
    if (asArray(decision.conditions).length) appendList(target, decision.conditions, "condition-list");
    const badge = dom("winnerVerdict");
    if (badge) {
      const verdict = Object.hasOwn(VERDICT_LABELS, decision.verdict) ? decision.verdict : "PENDING";
      badge.dataset.verdict = verdict;
      badge.textContent = verdictLabel(verdict);
    }
  }

  function renderLeaderboard(view) {
    const target = dom("leaderboard");
    if (!target) return;
    clearNode(target);
    const sorted = [...view.candidate_skus].sort((a, b) => {
      const aScore = clampScore((view.scorecards.find((card) => card.concept_id === a.id) || {}).total_score);
      const bScore = clampScore((view.scorecards.find((card) => card.concept_id === b.id) || {}).total_score);
      return bScore - aScore || String(a.id).localeCompare(String(b.id));
    });
    sorted.forEach((candidate, index) => {
      const card = view.scorecards.find((item) => item.concept_id === candidate.id) || {};
      const button = document.createElement("button");
      button.type = "button";
      button.className = "candidate-row";
      button.id = `candidate-tab-${safeText(candidate.id, 60).replace(/[^a-zA-Z0-9_-]/g, "")}`;
      button.dataset.candidateId = safeText(candidate.id, 80);
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", "candidateDetail");
      button.setAttribute("aria-selected", String(candidate.id === state.selectedId));
      button.tabIndex = candidate.id === state.selectedId ? 0 : -1;
      button.addEventListener("click", () => selectCandidate(candidate.id));
      button.addEventListener("keydown", (event) => handleCandidateKeys(event, sorted));
      appendText(button, "span", String(index + 1).padStart(2, "0"), "candidate-rank");
      const copy = document.createElement("span");
      copy.className = "candidate-row-copy";
      appendText(copy, "strong", candidate.name);
      appendText(copy, "small", PATH_LABELS[candidate.path] || "候选路径");
      button.appendChild(copy);
      appendText(button, "span", clampScore(card.total_score).toFixed(2), "candidate-row-score");
      const verdict = Object.hasOwn(VERDICT_LABELS, card.recommendation) ? card.recommendation : "PENDING";
      const badge = appendText(button, "span", verdictLabel(verdict), "candidate-verdict");
      badge.dataset.verdict = verdict;
      target.appendChild(button);
    });
    const count = dom("candidateCount");
    if (count) count.textContent = `${sorted.length} 个候选`;
  }

  function handleCandidateKeys(event, candidates) {
    const ids = candidates.map((item) => item.id);
    const current = Math.max(0, ids.indexOf(state.selectedId));
    let next = current;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") next = (current + 1) % ids.length;
    else if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = (current - 1 + ids.length) % ids.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = ids.length - 1;
    else return;
    event.preventDefault();
    selectCandidate(ids[next]);
    const nextTab = [...(dom("leaderboard")?.querySelectorAll("[data-candidate-id]") || [])]
      .find((item) => item.dataset.candidateId === String(ids[next]));
    nextTab?.focus();
  }

  function renderScorecard(candidate, card) {
    const body = dom("scoreMatrix");
    if (!body) return;
    clearNode(body);
    for (const dimension of asArray(card.dimensions)) {
      const row = document.createElement("tr");
      appendText(row, "th", dimension.label || dimension.key).scope = "row";
      const scoreCell = document.createElement("td");
      const score = clampScore(dimension.score);
      appendText(scoreCell, "span", score.toFixed(1), "dimension-score");
      const bar = document.createElement("span");
      bar.className = "score-bar";
      const fill = document.createElement("span");
      fill.style.width = `${score}%`;
      bar.appendChild(fill);
      scoreCell.appendChild(bar);
      row.appendChild(scoreCell);
      appendText(row, "td", `${Math.round(clampScore(Number(dimension.weight) * 100))}%`);
      const rationaleCell = document.createElement("td");
      appendText(rationaleCell, "span", dimension.rationale, "dimension-rationale");
      appendText(
        rationaleCell,
        "small",
        dimension.rationale_source === "qwen3.7-plus" ? "Qwen 动态解释" : "来源待确认",
        "rationale-source",
      );
      row.appendChild(rationaleCell);
      const evidenceCell = document.createElement("td");
      const ids = asArray(dimension.evidence_ids);
      evidenceCell.appendChild(evidenceButton(ids[0], ids.length ? `证据 ${ids.length}` : "无证据"));
      row.appendChild(evidenceCell);
      body.appendChild(row);
    }
    const total = dom("selectedScore");
    if (total) total.textContent = clampScore(card.total_score).toFixed(2);
    const name = dom("selectedScoreName");
    if (name) name.textContent = safeText(candidate.name, 100);
  }

  function renderCandidateDetail(candidate) {
    const target = dom("candidateDetail");
    if (!target) return;
    clearNode(target);
    appendText(target, "h3", candidate.name || "候选 SKU");
    appendText(target, "p", PATH_LABELS[candidate.path] || "候选路径", "path-label");
    appendText(target, "p", candidate.one_liner, "lead-copy");
    appendText(target, "h4", "目标客群");
    appendText(target, "p", candidate.target_segment);
    appendText(target, "h4", "价值主张");
    appendText(target, "p", candidate.value_proposition);
    appendText(target, "h4", "产品要点");
    appendList(target, candidate.key_features);
    if (asArray(candidate.revision_notes).length) {
      appendText(target, "h4", "下一轮验证记录");
      appendList(target, candidate.revision_notes, "revision-list");
    }
  }

  function renderInsights(view) {
    const trendTarget = dom("trendSignals");
    const opportunityTarget = dom("opportunityList");
    clearNode(trendTarget);
    clearNode(opportunityTarget);
    for (const trend of view.trend_signals) {
      const item = document.createElement("article");
      item.className = "signal-item";
      appendText(item, "h4", trend.name);
      appendText(item, "p", trend.summary);
      const ids = asArray(trend.evidence_ids);
      item.appendChild(evidenceButton(ids[0], ids[0] ? "查看来源" : "无证据"));
      trendTarget?.appendChild(item);
    }
    const opportunities = asArray(view.consumer_insights.opportunities);
    for (const opportunity of opportunities) {
      const item = document.createElement("article");
      item.className = "signal-item";
      appendText(item, "h4", opportunity.aspect);
      appendText(item, "p", opportunity.statement);
      appendText(item, "span", `机会分 ${Number(opportunity.opportunity_score || 0).toFixed(2)}`, "signal-score");
      const ids = asArray(opportunity.evidence_ids);
      item.appendChild(evidenceButton(ids[0], ids[0] ? "查看依据" : "无证据"));
      opportunityTarget?.appendChild(item);
    }
    if (dom("trendCount")) dom("trendCount").textContent = `${view.trend_signals.length} 条信号`;
    if (dom("opportunityCount")) dom("opportunityCount").textContent = `${opportunities.length} 个机会`;
    if (dom("insightScope")) dom("insightScope").textContent = `${Number(view.consumer_insights.review_count || 0)} 条研究样本`;
  }

  function renderValidation(view, candidate) {
    const target = dom("launchValidation");
    clearNode(target);
    const byCandidate = asObject(view.launch_validation.by_candidate);
    const validation = asObject(byCandidate[candidate.id]);
    const acceptance = Number(validation.average_acceptance);
    if (dom("acceptanceSummary")) {
      dom("acceptanceSummary").textContent = Number.isFinite(acceptance)
        ? `模拟接受度 ${Math.round(acceptance * 100)}%`
        : "暂无模拟结果";
    }
    const nps = asObject(validation.nps);
    appendText(target, "p", `模拟 NPS 推演：${Number.isFinite(Number(nps.score)) ? Number(nps.score).toFixed(1) : "—"}`, "validation-summary");
    appendText(target, "p", nps.rationale, "muted-copy");
    for (const interview of asArray(validation.interviews)) {
      const item = document.createElement("article");
      item.className = "validation-item";
      appendText(item, "h4", interview.persona_name || interview.segment || "用户镜像");
      appendText(item, "p", interview.segment);
      appendText(item, "span", interviewVerdictLabel(interview.verdict), "validation-verdict");
      if (asArray(interview.objections).length) {
        appendText(item, "h5", "主要异议");
        appendList(item, interview.objections, "objection-list");
      }
      if (asArray(interview.must_fixes).length) {
        appendText(item, "h5", "必须修正");
        appendList(item, interview.must_fixes, "revision-list");
      }
      const transcript = asArray(interview.transcript);
      if (transcript.length) {
        const details = document.createElement("details");
        details.className = "interview-transcript";
        appendText(details, "summary", `查看 ${transcript.length} 轮合成访谈`);
        for (const turn of transcript) {
          const row = document.createElement("div");
          row.className = "transcript-turn";
          appendText(row, "strong", `问：${safeText(turn.question, 100)}`);
          appendText(row, "p", `答：${safeText(turn.answer, 220)}`);
          details.appendChild(row);
        }
        item.appendChild(details);
      }
      target?.appendChild(item);
    }
  }

  function renderQuality(view, candidate) {
    const target = dom("qualityRisk");
    clearNode(target);
    const assessment = asObject(asObject(view.quality_audit.by_candidate)[candidate.id]);
    if (dom("qualityStatus")) dom("qualityStatus").textContent = assessmentLabel(assessment.overall);
    const metrics = [
      ["成本与毛利", assessment.gross_margin_score],
      ["供应链", assessment.supply_feasibility_score],
      ["IP/合规", assessment.ip_compliance_score],
      ["本地化", assessment.localization_score],
    ];
    const metricGrid = document.createElement("div");
    metricGrid.className = "compact-metrics";
    for (const [label, value] of metrics) {
      const metric = document.createElement("div");
      appendText(metric, "span", label);
      appendText(metric, "strong", Number.isFinite(Number(value)) ? clampScore(value).toFixed(0) : "—");
      metricGrid.appendChild(metric);
    }
    target?.appendChild(metricGrid);
    const narratives = [
      ["技术路径", assessment.technical],
      ["供应链", assessment.supply_chain],
      ["成本与 BOM", assessment.bom_cost],
      ["合规", assessment.compliance],
      ["质量", assessment.quality],
      ["毛利", assessment.gross_margin],
      ["供应商交期", assessment.supplier_lead_time],
      ["IP 授权", assessment.ip_authorization],
      ["区域合规", assessment.regional_compliance],
      ["本地化", assessment.localization],
    ].filter((entry) => String(entry[1] || "").trim());
    if (narratives.length) {
      const details = document.createElement("details");
      details.className = "feasibility-narratives";
      appendText(details, "summary", "查看商品化判断");
      const list = document.createElement("dl");
      for (const [label, value] of narratives) {
        appendText(list, "dt", label);
        appendText(list, "dd", value);
      }
      details.appendChild(list);
      target?.appendChild(details);
    }
    for (const risk of asArray(assessment.risks)) {
      const item = document.createElement("article");
      item.className = "risk-item";
      item.dataset.severity = ["low", "medium", "high"].includes(risk.severity) ? risk.severity : "medium";
      appendText(item, "h4", riskAreaLabel(risk.area));
      appendText(
        item,
        "span",
        risk.source === "deterministic_guardrail" ? "本地硬闸口" : "Qwen 动态风险假设",
        "risk-source",
      );
      appendText(item, "p", risk.description);
      appendText(item, "small", `缓解措施：${safeText(risk.mitigation, 240)}`);
      target?.appendChild(item);
    }
  }

  function renderProposal(view) {
    const target = dom("winnerProposal");
    clearNode(target);
    const prfaq = asObject(view.portfolio_decision.prfaq);
    appendText(target, "h3", prfaq.headline || view.portfolio_decision.winner_name || "榜首提案");
    appendText(target, "p", prfaq.subheading, "proposal-subheading");
    appendText(target, "p", prfaq.summary, "proposal-summary");
    if (prfaq.customer_quote || prfaq.maker_quote) {
      const quotes = document.createElement("div");
      quotes.className = "proposal-quotes";
      for (const [label, value] of [
        ["合成用户表达", prfaq.customer_quote],
        ["商品团队行动", prfaq.maker_quote],
      ]) {
        if (!value) continue;
        const quote = document.createElement("blockquote");
        appendText(quote, "p", value);
        appendText(quote, "cite", label);
        quotes.appendChild(quote);
      }
      target.appendChild(quotes);
    }
    if (prfaq.call_to_action) appendText(target, "p", prfaq.call_to_action, "proposal-action");
    for (const section of [
      ["外部问答", prfaq.external_faq],
      ["内部决策问答", prfaq.internal_faq],
    ]) {
      if (!asArray(section[1]).length) continue;
      appendText(target, "h4", section[0]);
      for (const faq of asArray(section[1])) {
        const item = document.createElement("details");
        appendText(item, "summary", faq.question);
        appendText(item, "p", faq.answer);
        target?.appendChild(item);
      }
    }
  }

  function renderEvidence(sourceId) {
    const target = dom("evidenceDetail");
    if (!target || !state.view) return;
    clearNode(target);
    const evidence = asObject(state.view.evidence_index[sourceId]);
    const mode = dom("evidenceMode");
    if (!evidence.source_id) {
      if (mode) mode.textContent = "未找到来源";
      appendText(target, "p", "当前运行未返回这条证据。", "empty-copy");
      return;
    }
    if (mode) mode.textContent = evidence.is_demo ? "合成演示来源" : "公开来源";
    appendText(target, "h4", evidence.source_id);
    appendText(target, "p", evidence.text, "evidence-copy");
    appendText(target, "p", `${evidence.brand || "未知品牌"} · ${evidence.product || "未标商品"} · ${evidence.date || "日期未标"}`, "evidence-meta");
    const url = safeHttpUrl(evidence.url);
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "打开公开来源";
      target.appendChild(link);
    } else {
      appendText(target, "span", "演示来源不可外链", "demo-source");
    }
  }

  function renderAudit(view) {
    const rubricTarget = dom("rubricMetrics");
    const baselineTarget = dom("baselineComparison");
    const toolTarget = dom("toolAudit");
    clearNode(rubricTarget);
    clearNode(baselineTarget);
    clearNode(toolTarget);
    const rubric = asObject(view.quality_audit.rubric);
    for (const key of ["groundedness", "faithfulness", "citation_hit_rate", "opportunity_coverage", "persona_fidelity", "explainability", "overall"]) {
      const value = Number(rubric[key]);
      const row = document.createElement("div");
      row.className = "metric-row";
      appendText(row, "span", metricLabel(key));
      appendText(row, "strong", Number.isFinite(value) ? value.toFixed(2) : "—");
      rubricTarget?.appendChild(row);
    }
    const baseline = asObject(view.audit.experience_baseline);
    appendText(baselineTarget, "p", baseline.narrative, "muted-copy");
    const armA = asObject(baseline.arm_a);
    const armB = asObject(baseline.arm_b);
    for (const [label, key] of [["机会覆盖", "opportunity_coverage"], ["证据引用", "evidence_citations"], ["模拟 NPS", "nps_prediction"]]) {
      const row = document.createElement("div");
      row.className = "comparison-row";
      appendText(row, "span", label);
      appendText(row, "span", `经验 ${Number(armA[key] || 0).toFixed(2)}`);
      appendText(row, "strong", `Agent ${Number(armB[key] || 0).toFixed(2)}`);
      baselineTarget?.appendChild(row);
    }
    for (const call of asArray(view.audit.tool_calls)) {
      const row = document.createElement("div");
      row.className = "tool-row";
      appendText(row, "strong", call.tool_name || "read_tool");
      const status = call.status === "success" ? "成功" : "已降级";
      appendText(row, "span", status);
      toolTarget?.appendChild(row);
    }
    if (dom("auditSummary")) dom("auditSummary").textContent = `${asArray(view.audit.tool_calls).length} 次只读工具调用`;
  }

  function selectCandidate(id) {
    if (!state.view) return;
    const selected = selectCandidateModel(state.view, id);
    if (!selected.candidate.id) return;
    state.selectedId = selected.candidate.id;
    renderLeaderboard(state.view);
    const selectedTab = dom("leaderboard")?.querySelector(`[data-candidate-id="${CSS.escape(String(state.selectedId))}"]`);
    const detailPanel = dom("candidateDetail");
    if (detailPanel) detailPanel.setAttribute("aria-labelledby", selectedTab?.id || "candidateDetailTitle");
    renderScorecard(selected.candidate, selected.scorecard);
    renderCandidateDetail(selected.candidate);
    renderValidation(state.view, selected.candidate);
    renderQuality(state.view, selected.candidate);
  }

  function renderView(rawView, expectedBinding = {}) {
    const view = validateViewContract(rawView, expectedBinding);
    state.view = view;
    state.selectedId = view.winner_id || view.candidate_skus[0]?.id || null;
    renderWinner(view);
    renderLeaderboard(view);
    if (state.selectedId) selectCandidate(state.selectedId);
    renderInsights(view);
    renderProposal(view);
    renderAudit(view);
    const generation = requireStrictGeneration(view.generation_provenance);
    if (dom("generationBadge")) {
      dom("generationBadge").textContent = "Qwen 动态生成 2/2 · 数值与硬闸口本地锁定";
    }
    const provenance = view.data_provenance;
    if (dom("provenanceSummary")) {
      dom("provenanceSummary").textContent = safeText(
        `${decisionInputSummary(view.decision_input)} · ${provenance.disclaimer || "研究数据边界待确认"}`,
        420,
      );
    }
    if (dom("runMeta")) {
      const provider = safeText(view.effective_provider || view.provider || "qwen", 40);
      const model = safeText(view.model || "qwen3.7-plus", 80);
      dom("runMeta").textContent = `${safeText(view.run_id, 80)} · ${Number(view.elapsed_seconds || 0).toFixed(2)}s · ${provider} · ${model}`;
    }
    for (const [id, kind] of [["fullReportLink", "full"], ["openingReportLink", "opening"]]) {
      const link = dom(id);
      if (!link || !view.run_id) continue;
      link.href = apiUrl(`api/report?run_id=${encodeURIComponent(view.run_id)}&kind=${kind}`);
      link.removeAttribute("aria-disabled");
      link.dataset.reportKind = kind;
    }
    if (dom("jsonDownloadBtn")) dom("jsonDownloadBtn").disabled = false;
    syncFormState();
    const firstEvidence = Object.keys(view.evidence_index)[0];
    if (firstEvidence) renderEvidence(firstEvidence);
  }

  function resetWorkspaceForRun() {
    state.reportToken += 1;
    state.reportMarkdown = "";
    closeReportDialog();
    for (const id of [
      "winnerContent",
      "leaderboard",
      "scoreMatrix",
      "trendSignals",
      "opportunityList",
      "candidateDetail",
      "launchValidation",
      "qualityRisk",
      "winnerProposal",
      "evidenceDetail",
      "rubricMetrics",
      "baselineComparison",
      "toolAudit",
    ]) clearNode(dom(id));

    const textById = {
      winnerVerdict: "待评审",
      candidateCount: "0 个候选",
      selectedScore: "--",
      selectedScoreName: "正在生成新一轮候选评分",
      trendCount: "0 条信号",
      opportunityCount: "0 个机会",
      insightScope: "正在读取研究样本",
      acceptanceSummary: "待运行",
      qualityStatus: "待运行",
      evidenceMode: "请选择证据",
      auditSummary: "等待 Agent 工具调用记录",
      provenanceSummary: "Qwen 正在生成本轮动态决策",
      generationBadge: "等待 Qwen 动态生成",
      runMeta: "正在生成新的运行记录",
    };
    for (const [id, value] of Object.entries(textById)) {
      const node = dom(id);
      if (node) node.textContent = value;
    }
    const verdict = dom("winnerVerdict");
    if (verdict) verdict.dataset.verdict = "PENDING";
    for (const id of ["fullReportLink", "openingReportLink"]) {
      const link = dom(id);
      if (!link) continue;
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
    }
    if (dom("jsonDownloadBtn")) dom("jsonDownloadBtn").disabled = true;
    if (dom("reportDownloadBtn")) dom("reportDownloadBtn").disabled = true;
    if (dom("reportMarkdown")) dom("reportMarkdown").textContent = "";
    if (dom("reportStatus")) dom("reportStatus").textContent = "选择报告后加载。";
  }

  function setError(message) {
    const alert = dom("runtimeAlert");
    if (alert) {
      alert.hidden = false;
      alert.textContent = safeText(message || "运行失败，请稍后重试。", 220);
    }
  }

  function resetWorkspace() {
    for (const id of [
      "winnerContent",
      "leaderboard",
      "scoreMatrix",
      "candidateDetail",
      "trendSignals",
      "opportunityList",
      "launchValidation",
      "qualityRisk",
      "winnerProposal",
      "evidenceDetail",
      "rubricMetrics",
      "baselineComparison",
      "toolAudit",
    ]) clearNode(dom(id));
    const defaults = {
      candidateCount: "0 个候选",
      selectedScore: "--",
      selectedScoreName: "运行后查看候选评分",
      trendCount: "0 条信号",
      opportunityCount: "0 个机会",
      acceptanceSummary: "待运行",
      qualityStatus: "待运行",
      evidenceMode: "请选择证据",
      auditSummary: "等待 Agent 工具调用记录",
      insightScope: "等待研究样本",
      provenanceSummary: "等待 Qwen 生成本轮可追溯决策",
      generationBadge: "等待 Qwen 动态生成",
      runMeta: "尚未生成运行记录",
    };
    for (const [id, value] of Object.entries(defaults)) {
      const element = dom(id);
      if (element) element.textContent = value;
    }
    const verdict = dom("winnerVerdict");
    if (verdict) {
      verdict.dataset.verdict = "PENDING";
      verdict.textContent = VERDICT_LABELS.PENDING;
    }
    for (const id of ["fullReportLink", "openingReportLink"]) {
      const link = dom(id);
      if (!link) continue;
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
    }
    if (dom("jsonDownloadBtn")) dom("jsonDownloadBtn").disabled = true;
    if (dom("reportDownloadBtn")) dom("reportDownloadBtn").disabled = true;
    if (dom("reportMarkdown")) dom("reportMarkdown").textContent = "";
    if (dom("reportStatus")) dom("reportStatus").textContent = "选择报告后加载。";
    renderWinner(normalizeView({}));
  }

  function setFieldErrors(errors, showErrors) {
    const form = dom("runForm");
    if (!form) return;
    for (const errorNode of form.querySelectorAll("[data-error-for]")) {
      const field = errorNode.dataset.errorFor;
      errorNode.textContent = showErrors ? safeText(errors[field] || "", 100) : "";
    }
    for (const control of form.querySelectorAll("[name]")) {
      const invalid = Boolean(showErrors && errors[control.name]);
      control.setAttribute("aria-invalid", String(invalid));
    }
  }

  function updateCharacterCounts() {
    const brief = dom("brief")?.value || "";
    const constraints = dom("constraints")?.value || "";
    if (dom("briefCount")) dom("briefCount").textContent = `${brief.length}/500`;
    if (dom("constraintsCount")) dom("constraintsCount").textContent = `${constraints.length}/300`;
  }

  function updateCustomCategory() {
    const isOther = dom("productCategory")?.value === "other";
    const field = dom("customCategoryField");
    const input = dom("customCategory");
    if (field) field.hidden = !isOther;
    if (input) {
      input.required = isOther;
      input.disabled = state.running || !isOther;
    }
  }

  function updateObjectiveLimit() {
    const options = [...(dom("runForm")?.querySelectorAll('[name="objectives"]') || [])];
    const checkedCount = options.filter((item) => item.checked).length;
    for (const option of options) option.disabled = state.running || (checkedCount >= 4 && !option.checked);
  }

  function syncFormState(showErrors = state.formTouched) {
    const form = dom("runForm");
    if (!form) return { input: {}, validation: { valid: false, errors: {} } };
    updateCustomCategory();
    updateObjectiveLimit();
    updateCharacterCounts();
    const input = readDecisionInput(form);
    const validation = validateDecisionInput(input);
    setFieldErrors(validation.errors, showErrors);
    const runButton = dom("runBtn");
    const rerunButton = dom("rerunBtn");
    const runnable = canRunDecision(validation, state.running, state.serviceReady);
    if (runButton) runButton.disabled = !runnable;
    if (rerunButton) rerunButton.disabled = !runnable || !state.view;
    return { input, validation };
  }

  function setFormRunning(running) {
    state.running = running;
    for (const control of dom("runForm")?.querySelectorAll("[data-request-control]") || []) {
      control.disabled = running;
    }
    if (dom("clearBtn")) dom("clearBtn").disabled = running;
    syncFormState();
  }

  function closeReportDialog() {
    const dialog = dom("reportDialog");
    if (!dialog) return;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
  }

  function selectReportKind(kind) {
    state.reportKind = kind === "opening" ? "opening" : "full";
    for (const tab of dom("reportDialog")?.querySelectorAll("[data-report-kind]") || []) {
      const selected = tab.dataset.reportKind === state.reportKind;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected) dom("reportPanel")?.setAttribute("aria-labelledby", tab.id);
    }
  }

  async function loadReport() {
    if (!state.view?.run_id) return;
    const token = ++state.reportToken;
    const status = dom("reportStatus");
    const output = dom("reportMarkdown");
    const retry = dom("reportRetryBtn");
    const download = dom("reportDownloadBtn");
    if (status) status.textContent = "正在加载报告…";
    if (output) output.textContent = "";
    if (retry) retry.disabled = true;
    if (download) download.disabled = true;
    state.reportMarkdown = "";
    try {
      const url = `api/report?run_id=${encodeURIComponent(state.view.run_id)}&kind=${state.reportKind}`;
      const response = await fetch(apiUrl(url), {
        headers: accessHeaders(ACCESS_TOKEN, { Accept: "application/json, text/markdown, text/plain" }),
      });
      if (!response.ok) throw new Error("report");
      const raw = await response.text();
      let markdown = raw;
      try {
        const payload = JSON.parse(raw);
        markdown = typeof payload.markdown === "string" ? payload.markdown : raw;
      } catch (_error) {
        markdown = raw;
      }
      if (token !== state.reportToken) return;
      state.reportMarkdown = markdown;
      if (output) output.textContent = markdown;
      if (status) status.textContent = markdown ? "报告已加载" : "报告内容为空";
      if (download) download.disabled = !markdown;
    } catch (_error) {
      if (token !== state.reportToken) return;
      if (status) status.textContent = "报告加载失败，请重试。";
      if (output) output.textContent = "";
    } finally {
      if (token === state.reportToken && retry) retry.disabled = false;
    }
  }

  function openReport(kind, event) {
    event?.preventDefault();
    if (!state.view?.run_id) return;
    selectReportKind(kind);
    const dialog = dom("reportDialog");
    if (dialog && typeof dialog.showModal === "function") dialog.showModal();
    else dialog?.setAttribute("open", "");
    loadReport();
  }

  function downloadBlob(content, type, filename) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function downloadReport() {
    if (!state.view?.run_id || !state.reportMarkdown) return;
    const runId = safeDownloadId(state.view.run_id);
    downloadBlob(state.reportMarkdown, "text/markdown;charset=utf-8", `trend2sku-${runId}-${state.reportKind}.md`);
  }

  function downloadCurrentResult() {
    if (!state.view?.run_id) return;
    const runId = safeDownloadId(state.view.run_id);
    downloadBlob(`${JSON.stringify(state.view, null, 2)}\n`, "application/json;charset=utf-8", `trend2sku-${runId}-result.json`);
  }

  function clearAll() {
    state.runToken += 1;
    state.reportToken += 1;
    state.eventSource?.close();
    state.eventSource = null;
    state.view = null;
    state.selectedId = null;
    state.formTouched = false;
    state.running = false;
    dom("runForm")?.reset();
    closeReportDialog();
    resetWorkspace();
    setRuntime(createRuntimeSnapshot(), "就绪，等待运行");
    const alert = dom("runtimeAlert");
    if (alert) alert.hidden = true;
    const warning = dom("warningArea");
    if (warning) warning.hidden = true;
    syncFormState(false);
    dom("brief")?.focus();
  }

  async function startRun() {
    state.formTouched = true;
    const { input, validation } = syncFormState(true);
    if (!validation.valid) {
      const firstInvalid = dom("runForm")?.querySelector('[aria-invalid="true"]');
      firstInvalid?.focus();
      return;
    }
    if (!state.serviceReady) {
      setError("Qwen 服务尚未就绪，请确认后端连接与模型配置。");
      return;
    }
    state.runToken += 1;
    const token = state.runToken;
    state.eventSource?.close();
    state.eventSource = null;
    state.view = null;
    state.selectedId = null;
    const requestedThreadId = createClientThreadId();
    let streamBinding = { runId: null, threadId: requestedThreadId };
    resetWorkspace();
    resetWorkspaceForRun();
    setRuntime(reduceRuntime(state.runtime, { type: "run_started" }), "Agent 正在调用 Qwen 并读取研究样本");
    const alert = dom("runtimeAlert");
    if (alert) alert.hidden = true;
    setFormRunning(true);
    let source;
    try {
      const ticket = await createStreamTicket(input, requestedThreadId);
      if (token !== state.runToken) return;
      source = new EventSource(apiUrl(ticket.stream_url));
    } catch (_error) {
      state.runtime = reduceRuntime(state.runtime, { type: "run_error" });
      setRuntime(state.runtime, "无法建立运行连接");
      setError("当前浏览器无法建立 Agent 运行连接。");
      setFormRunning(false);
      return;
    }
    state.eventSource = source;
    source.onmessage = (event) => {
      if (token !== state.runToken) return;
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (_error) {
        state.runtime = reduceRuntime(state.runtime, { type: "run_error" });
        setRuntime(state.runtime, "响应格式异常");
        setError("服务返回了无法解析的运行事件。");
        source.close();
        if (state.eventSource === source) state.eventSource = null;
        setFormRunning(false);
        return;
      }
      try {
        streamBinding = bindSseEnvelope(streamBinding, message);
        if (state.runtime.terminal && message.type !== "done") return;
        if (message.type === "trace") {
          const trace = asObject(message.event);
          state.runtime = reduceRuntime(state.runtime, { type: "trace", event: trace });
          if (trace.kind === "tool_call" && trace.status === "error") {
            state.runtime = reduceRuntime(state.runtime, { type: "tool_warning", message: `${trace.tool_name || "只读工具"} 已使用确定性降级` });
          }
          if (trace.kind === "provider_fallback") {
            state.runtime = reduceRuntime(state.runtime, {
              type: "tool_warning",
              message: `${trace.configured_provider || "远程模型"} 不可用，本轮已切换离线确定性模式`,
            });
          }
          setRuntime(state.runtime, runtimeTraceMessage(trace));
        } else if (message.type === "result") {
          renderView(message.view, streamBinding);
          state.runtime = reduceRuntime(state.runtime, { type: "result_received" });
          setRuntime(state.runtime, "决策组合已生成");
        } else if (message.type === "error") {
          state.runtime = reduceRuntime(state.runtime, { type: "run_error" });
          setRuntime(state.runtime, "运行失败");
          setError(message.message || "运行失败，请稍后重试。");
          source.close();
          if (state.eventSource === source) state.eventSource = null;
          setFormRunning(false);
        } else if (message.type === "done") {
          const alreadyTerminal = state.runtime.terminal;
          state.runtime = reduceRuntime(state.runtime, { type: "done" });
          source.close();
          if (state.eventSource === source) state.eventSource = null;
          setFormRunning(false);
          if (!alreadyTerminal) {
            setRuntime(state.runtime, "运行未返回决策结果");
            setError("运行流已结束，但没有收到可展示的决策结果。");
          }
        }
      } catch (_error) {
        state.runtime = reduceRuntime(state.runtime, { type: "run_error" });
        setRuntime(state.runtime, "数据渲染失败");
        setError("运行结果未通过前端结构校验。");
        source.close();
        if (state.eventSource === source) state.eventSource = null;
        setFormRunning(false);
      }
    };
    let recoveryStarted = false;
    source.onerror = () => {
      if (token !== state.runToken) return;
      if (recoveryStarted) return;
      recoveryStarted = true;
      source.close();
      if (state.eventSource === source) state.eventSource = null;
      if (state.runtime.terminal) {
        setFormRunning(false);
        return;
      }
      setRuntime(state.runtime, "实时连接波动，正在取回本轮结果");
      const recoveryAlert = dom("runtimeAlert");
      if (recoveryAlert) recoveryAlert.hidden = true;
      pollRunResult(requestedThreadId)
        .then((view) => {
          if (token !== state.runToken) return;
          renderView(view, streamBinding);
          state.runtime = reduceRuntime(state.runtime, { type: "result_received" });
          setRuntime(state.runtime, "决策组合已恢复");
        })
        .catch((_error) => {
          if (token !== state.runToken) return;
          state.runtime = reduceRuntime(state.runtime, { type: "disconnected" });
          setRuntime(state.runtime, "结果取回超时");
          setError("本轮运行仍未返回结果，请稍后再试。");
        })
        .finally(() => {
          if (token === state.runToken) setFormRunning(false);
        });
    };
  }

  async function checkHealth() {
    const badge = dom("serviceBadge");
    try {
      const response = await fetch(apiUrl("api/health"), {
        headers: accessHeaders(ACCESS_TOKEN, { Accept: "application/json" }),
      });
      if (!response.ok) throw new Error("health");
      const health = await response.json();
      const provider = safeText(health.effective_provider || health.provider || "", 30);
      const model = safeText(health.model || "", 40);
      const mode = safeText(health.decision_mode || "", 80);
      state.serviceReady = provider === "qwen"
        && model === "qwen3.7-plus"
        && mode === "qwen_strict_dynamic_with_deterministic_guardrails";
      if (badge) {
        badge.dataset.service = state.serviceReady ? "online" : "offline";
        badge.textContent = state.serviceReady
          ? `${provider} · ${model} · 严格动态`
          : "Qwen 3.7 Plus 未就绪";
      }
      syncFormState();
    } catch (_error) {
      state.serviceReady = false;
      if (badge) {
        badge.dataset.service = "offline";
        badge.textContent = "服务未连接";
      }
      syncFormState();
    }
  }

  function boot() {
    const form = dom("runForm");
    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      startRun();
    });
    for (const eventName of ["input", "change"]) {
      form?.addEventListener(eventName, () => {
        state.formTouched = true;
        syncFormState(true);
      });
    }
    dom("clearBtn")?.addEventListener("click", clearAll);
    dom("rerunBtn")?.addEventListener("click", startRun);
    dom("fullReportLink")?.addEventListener("click", (event) => openReport("full", event));
    dom("openingReportLink")?.addEventListener("click", (event) => openReport("opening", event));
    for (const tab of dom("reportDialog")?.querySelectorAll("[data-report-kind]") || []) {
      tab.addEventListener("click", () => {
        selectReportKind(tab.dataset.reportKind);
        loadReport();
      });
    }
    dom("reportRetryBtn")?.addEventListener("click", loadReport);
    dom("reportDownloadBtn")?.addEventListener("click", downloadReport);
    dom("jsonDownloadBtn")?.addEventListener("click", downloadCurrentResult);
    dom("reportCloseBtn")?.addEventListener("click", closeReportDialog);
    dom("reportDoneBtn")?.addEventListener("click", closeReportDialog);
    setRuntime(state.runtime, "就绪，等待运行");
    resetWorkspace();
    syncFormState(false);
    checkHealth();
    if (new URLSearchParams(location.search).get("auto") === "1") window.setTimeout(startRun, 300);
  }

  window.Trend2SKUApp = {
    ...publicApi,
    renderViewForTest: renderView,
    selectCandidate,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
}
