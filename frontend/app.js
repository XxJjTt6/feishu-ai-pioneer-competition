"use strict";

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

const CONCEPT_ASSETS = {
  "C-TREND": "static/assets/miniso-v1/city-scent-charm-v1.png",
  "C-VOC": "static/assets/miniso-v1/mood-charm-v1.png",
  "C-WHITESPACE": "static/assets/miniso-v1/cocreate-patch-kit-v1.png",
};

const SSE_MESSAGE_TYPES = new Set(["heartbeat", "trace", "result", "error", "done"]);

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
  if (action.type === "result_received") return { ...next, phase: "complete", terminal: true };
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
  normalizeView,
  validateViewContract,
  bindSseEnvelope,
  createClientThreadId,
  selectCandidateModel,
  createRuntimeSnapshot,
  reduceRuntime,
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
    button.dataset.evidenceId = safeText(sourceId, 160);
    button.addEventListener("click", () => renderEvidence(sourceId));
    return button;
  }

  function conceptAsset(candidateId) {
    return CONCEPT_ASSETS[candidateId] || CONCEPT_ASSETS["C-VOC"];
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
    const image = document.createElement("img");
    image.className = "concept-thumb";
    image.src = conceptAsset(winner.id);
    image.alt = `${safeText(winner.name, 80)}概念示意`;
    layout.appendChild(image);
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
      appendText(row, "td", dimension.rationale, "dimension-rationale");
      const evidenceCell = document.createElement("td");
      const ids = asArray(dimension.evidence_ids);
      if (ids.length) evidenceCell.appendChild(evidenceButton(ids[0], `证据 ${ids.length}`));
      else evidenceCell.textContent = "—";
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
    const image = document.createElement("img");
    image.className = "candidate-visual";
    image.src = conceptAsset(candidate.id);
    image.alt = `${safeText(candidate.name, 80)}概念示意`;
    target.appendChild(image);
    appendText(target, "p", "概念示意", "visual-caption");
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
      if (ids[0]) item.appendChild(evidenceButton(ids[0], "查看来源"));
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
      if (ids[0]) item.appendChild(evidenceButton(ids[0], "查看依据"));
      opportunityTarget?.appendChild(item);
    }
    if (dom("trendCount")) dom("trendCount").textContent = `${view.trend_signals.length} 条信号`;
    if (dom("opportunityCount")) dom("opportunityCount").textContent = `${opportunities.length} 个机会`;
    if (dom("insightScope")) dom("insightScope").textContent = `${Number(view.consumer_insights.review_count || 0)} 条离线演示样本`;
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
    appendText(target, "p", `离线 NPS 推演：${Number.isFinite(Number(nps.score)) ? Number(nps.score).toFixed(1) : "—"}`, "validation-summary");
    appendText(target, "p", nps.rationale, "muted-copy");
    for (const interview of asArray(validation.interviews)) {
      const item = document.createElement("article");
      item.className = "validation-item";
      appendText(item, "h4", interview.persona_name || interview.segment || "用户镜像");
      appendText(item, "p", interview.segment);
      appendText(item, "span", safeText(interview.verdict, 40), "validation-verdict");
      if (asArray(interview.objections).length) appendList(item, interview.objections, "objection-list");
      target?.appendChild(item);
    }
  }

  function renderQuality(view, candidate) {
    const target = dom("qualityRisk");
    clearNode(target);
    const assessment = asObject(asObject(view.quality_audit.by_candidate)[candidate.id]);
    if (dom("qualityStatus")) dom("qualityStatus").textContent = safeText(assessment.overall || "待校准", 40);
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
    for (const risk of asArray(assessment.risks)) {
      const item = document.createElement("article");
      item.className = "risk-item";
      item.dataset.severity = ["low", "medium", "high"].includes(risk.severity) ? risk.severity : "medium";
      appendText(item, "h4", risk.area || "商品风险");
      appendText(item, "p", risk.description);
      appendText(item, "small", `缓解：${safeText(risk.mitigation, 240)}`);
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
      appendText(row, "span", key.replaceAll("_", " "));
      appendText(row, "strong", Number.isFinite(value) ? value.toFixed(2) : "—");
      rubricTarget?.appendChild(row);
    }
    const baseline = asObject(view.audit.experience_baseline);
    appendText(baselineTarget, "p", baseline.narrative, "muted-copy");
    const armA = asObject(baseline.arm_a);
    const armB = asObject(baseline.arm_b);
    for (const [label, key] of [["机会覆盖", "opportunity_coverage"], ["证据引用", "evidence_citations"], ["离线 NPS", "nps_prediction"]]) {
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
    const provenance = view.data_provenance;
    if (dom("provenanceSummary")) dom("provenanceSummary").textContent = safeText(provenance.disclaimer || "离线演示数据", 180);
    if (dom("runMeta")) dom("runMeta").textContent = `${safeText(view.run_id, 80)} · ${Number(view.elapsed_seconds || 0).toFixed(2)}s · ${safeText(view.effective_provider || view.provider || "offline", 40)}`;
    for (const [id, kind] of [["fullReportLink", "full"], ["openingReportLink", "opening"]]) {
      const link = dom(id);
      if (!link || !view.run_id) continue;
      link.href = `api/report?run_id=${encodeURIComponent(view.run_id)}&kind=${kind}`;
      link.removeAttribute("aria-disabled");
      link.target = "_blank";
      link.rel = "noopener";
    }
    const firstEvidence = Object.keys(view.evidence_index)[0];
    if (firstEvidence) renderEvidence(firstEvidence);
  }

  function resetWorkspaceForRun() {
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
      provenanceSummary: "离线演示数据，新一轮运行中",
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
      link.removeAttribute("target");
      link.removeAttribute("rel");
      link.setAttribute("aria-disabled", "true");
    }
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
      provenanceSummary: "离线演示数据，运行后生成可追溯结论",
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
      link.removeAttribute("target");
      link.setAttribute("aria-disabled", "true");
    }
    renderWinner(normalizeView({}));
  }

  function startRun() {
    const briefInput = dom("brief");
    const button = dom("runBtn");
    const brief = safeText(briefInput?.value || "", 500).trim();
    if (!brief) {
      setError("请输入决策简报。");
      briefInput?.focus();
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
    setRuntime(reduceRuntime(state.runtime, { type: "run_started" }), "Agent 正在读取离线演示样本");
    const alert = dom("runtimeAlert");
    if (alert) alert.hidden = true;
    if (button) button.disabled = true;
    let source;
    try {
      source = new EventSource(
        `api/stream?brief=${encodeURIComponent(brief)}&hitl=false&thread_id=${encodeURIComponent(requestedThreadId)}`,
      );
    } catch (_error) {
      state.runtime = reduceRuntime(state.runtime, { type: "run_error" });
      setRuntime(state.runtime, "无法建立运行连接");
      setError("当前浏览器无法建立 Agent 运行连接。");
      if (button) button.disabled = false;
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
        if (button) button.disabled = false;
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
          setRuntime(state.runtime, `${STAGE_LABELS[trace.node] || "工作流"} · ${trace.kind === "start" ? "运行中" : trace.kind === "end" ? "已完成" : "审计事件"}`);
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
          if (button) button.disabled = false;
        } else if (message.type === "done") {
          const alreadyTerminal = state.runtime.terminal;
          state.runtime = reduceRuntime(state.runtime, { type: "done" });
          source.close();
          if (state.eventSource === source) state.eventSource = null;
          if (button) button.disabled = false;
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
        if (button) button.disabled = false;
      }
    };
    source.onerror = () => {
      if (token !== state.runToken) return;
      source.close();
      if (state.eventSource === source) state.eventSource = null;
      if (button) button.disabled = false;
      state.runtime = reduceRuntime(state.runtime, { type: "disconnected" });
      if (!state.runtime.terminal || state.runtime.phase === "disconnected") {
        setRuntime(state.runtime, "连接已中断");
        setError("运行连接中断，请重新发起决策。");
      }
    };
  }

  async function checkHealth() {
    const badge = dom("serviceBadge");
    try {
      const response = await fetch("api/health", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("health");
      const health = await response.json();
      if (badge) {
        badge.dataset.service = "online";
        badge.textContent = `${safeText(health.effective_provider || health.provider || "offline", 30)} · 就绪`;
      }
    } catch (_error) {
      if (badge) {
        badge.dataset.service = "offline";
        badge.textContent = "服务未连接";
      }
    }
  }

  function boot() {
    dom("runForm")?.addEventListener("submit", (event) => {
      event.preventDefault();
      startRun();
    });
    setRuntime(state.runtime, "就绪，等待运行");
    resetWorkspace();
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
