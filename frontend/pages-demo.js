"use strict";
(function pagesDemoFactory(root, moduleLike) {
  "use strict";

  const DIMENSIONS = [
    { key: "trend_fit", label: "趋势匹配", weight: 0.20 },
    { key: "demand_strength", label: "需求强度", weight: 0.20 },
    { key: "differentiation", label: "差异化", weight: 0.15 },
    { key: "social_virality", label: "社交传播", weight: 0.15 },
    { key: "margin_potential", label: "成本与毛利", weight: 0.10 },
    { key: "supply_feasibility", label: "供应链可行性", weight: 0.10 },
    { key: "ip_compliance", label: "IP/合规", weight: 0.05 },
    { key: "localization_fit", label: "全球本地化", weight: 0.05 },
  ];
  const CATEGORY_LABELS = {
    plush: "毛绒玩具",
    fragrance_accessory: "香氛挂件",
    stationery: "文具套装",
    home_storage: "家居收纳",
    beauty_tool: "美妆工具",
    digital_accessory: "数码配件",
    other: "自定义商品",
  };
  const SEGMENT_LABELS = {
    student: "学生",
    young_professional: "年轻职场人",
    ip_fan: "IP 粉丝",
    gift: "礼赠人群",
    family: "家庭用户",
    collector: "收藏爱好者",
  };
  const MARKET_LABELS = {
    china: "中国",
    southeast_asia: "东南亚",
    japan_korea: "日韩",
    europe_america: "欧美",
    middle_east: "中东",
    global: "全球",
  };
  const PRICE_LABELS = { entry: "入门", mid: "中端", premium: "高端" };
  const IP_LABELS = { original: "原创 IP", licensed: "授权 IP", none: "无 IP", evaluate: "IP 待评估" };
  const OBJECTIVE_LABELS = {
    emotional: "情绪价值",
    social: "社交传播",
    margin: "毛利空间",
    supply_chain: "供应链",
    localization: "本地化",
  };
  const ALLOWED_OBJECTIVES = new Set(Object.keys(OBJECTIVE_LABELS));
  const BASE_SCORES = {
    "C-VOC": [82, 87, 78, 80, 74, 79, 91, 81],
    "C-TREND": [90, 77, 84, 88, 71, 73, 88, 86],
    "C-WHITESPACE": [76, 82, 92, 84, 81, 85, 92, 88],
  };
  const STAGES = [
    "insight",
    "trend_radar",
    "ideation",
    "user_mirror",
    "merchandise_expert",
    "hit_judge",
    "proposal",
  ];
  const DATA_BOUNDARY = "浏览器端固定规则离线演示，未调用远程模型，不代表真实用户研究、销量、ROI 或企业经营结论。";

  function text(value, limit = 500) {
    return String(value ?? "").replace(/[\u0000-\u001F\u007F]/g, " ").trim().slice(0, limit);
  }
  function clamp(value, lower = 0, upper = 100) {
    return Math.max(lower, Math.min(upper, Number(value) || 0));
  }
  function round(value, digits = 2) {
    const factor = 10 ** digits;
    return Math.round((Number(value) + Number.EPSILON) * factor) / factor;
  }
  function stableHash(value) {
    let hash = 2166136261;
    for (const character of String(value)) {
      hash ^= character.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }
  function choose(value, labels, fallback) {
    return Object.hasOwn(labels, value) ? value : fallback;
  }
  function normalizeInput(raw) {
    const source = raw && typeof raw === "object" ? raw : {};
    const productCategory = choose(String(source.product_category || ""), CATEGORY_LABELS, "plush");
    const objectives = [...new Set(
      (Array.isArray(source.objectives) ? source.objectives : [])
        .map(String)
        .filter((item) => ALLOWED_OBJECTIVES.has(item)),
    )].slice(0, 4);
    return {
      brief: text(source.brief || "面向兴趣消费用户设计可验证新品", 500),
      product_category: productCategory,
      custom_category: productCategory === "other" ? text(source.custom_category || "兴趣商品", 40) : "",
      target_segment: choose(String(source.target_segment || ""), SEGMENT_LABELS, "young_professional"),
      target_market: choose(String(source.target_market || ""), MARKET_LABELS, "global"),
      price_band: choose(String(source.price_band || ""), PRICE_LABELS, "mid"),
      ip_strategy: choose(String(source.ip_strategy || ""), IP_LABELS, "original"),
      objectives: objectives.length ? objectives : ["emotional"],
      constraints: text(source.constraints, 300),
    };
  }
  function categoryLabel(input) {
    return input.product_category === "other"
      ? text(input.custom_category || "兴趣商品", 40)
      : CATEGORY_LABELS[input.product_category];
  }
  function scoringSignature(input) {
    return [
      input.product_category,
      input.product_category === "other" ? input.custom_category : "",
      input.target_segment,
      input.target_market,
      input.price_band,
      input.ip_strategy,
      [...input.objectives].sort().join(","),
    ].join("|");
  }
  function dimensionScore(pathId, dimension, index, input) {
    let score = BASE_SCORES[pathId][index];
    const objectiveBoosts = {
      emotional: "demand_strength",
      social: "social_virality",
      margin: "margin_potential",
      supply_chain: "supply_feasibility",
      localization: "localization_fit",
    };
    for (const objective of input.objectives) {
      if (objectiveBoosts[objective] === dimension.key) score += 5;
    }
    if (input.price_band === "entry") {
      if (dimension.key === "supply_feasibility") score += 3;
      if (dimension.key === "margin_potential") score -= 2;
    }
    if (input.price_band === "premium") {
      if (dimension.key === "margin_potential" || dimension.key === "differentiation") score += 3;
    }
    if (input.target_market === "global" && dimension.key === "localization_fit") score += 3;
    if (input.target_segment === "student" && dimension.key === "demand_strength") score += 2;
    if (input.target_segment === "collector" && dimension.key === "differentiation") score += 3;
    if (dimension.key === "ip_compliance") {
      score = { original: 92, licensed: 78, none: 96, evaluate: 30 }[input.ip_strategy];
    }
    const jitter = (stableHash(`${scoringSignature(input)}|${pathId}|${dimension.key}`) % 5) - 2;
    return round(clamp(score + jitter, 25, 97), 1);
  }
  function highIpRisk(input) {
    if (input.ip_strategy !== "evaluate") return null;
    return {
      area: "IP/合规闸口",
      description: "IP 策略仍为待评估，授权范围或原创资产权属未确认，当前不得进入上市承诺。",
      severity: "high",
      mitigation: "在样件投放前完成权属、授权区域、授权期限和素材使用边界审查。",
    };
  }
  function buildCandidates(input) {
    const category = categoryLabel(input);
    const segment = SEGMENT_LABELS[input.target_segment];
    const market = MARKET_LABELS[input.target_market];
    const brief = text(input.brief, 72);
    return [
      {
        id: "C-VOC",
        name: `${segment}${category}需求共创款`,
        path: "voc_driven",
        one_liner: `围绕“${brief}”拆解高频使用任务，以需求证据优先验证。`,
        target_segment: segment,
        value_proposition: `用可感知的小功能降低${segment}的日常使用阻力，并形成可复购组合。`,
        key_features: ["核心任务模块化", `${PRICE_LABELS[input.price_band]}价格带组合`, "小批量反馈迭代"],
        differentiators: [{ statement: "先验证任务完成度，再扩展装饰与内容", evidence_ids: ["E-RULES"] }],
        tech_enablers: ["模块化物料清单", "门店反馈编码"],
      },
      {
        id: "C-TREND",
        name: `${market}${category}趋势限定款`,
        path: "trend_driven",
        one_liner: `把${market}趋势主题映射为可替换内容层，不把短期热度写进长期模具。`,
        target_segment: segment,
        value_proposition: "以限定内容创造新鲜感，同时保留全球复用的商品结构。",
        key_features: ["基础结构全球复用", `${market}内容层替换`, "限定批次节奏"],
        differentiators: [{ statement: "全球结构与区域表达分离", evidence_ids: ["E-RULES"] }],
        tech_enablers: ["柔性排产", "区域内容包"],
      },
      {
        id: "C-WHITESPACE",
        name: `${category}模块白空间款`,
        path: "whitespace_driven",
        one_liner: "避开同质化外观竞争，让用户通过组合与共创形成个人表达。",
        target_segment: segment,
        value_proposition: "用低门槛模块组合连接自用、礼赠与社交分享场景。",
        key_features: ["可替换功能模块", "开放式配件接口", "轻量共创任务"],
        differentiators: [{ statement: "把单品竞争转为模块生态验证", evidence_ids: ["E-RULES"] }],
        tech_enablers: ["通用接口规范", "小单快反"],
      },
    ];
  }
  function buildScorecards(input, candidates) {
    const blocking = highIpRisk(input);
    return candidates.map((candidate) => {
      const dimensions = DIMENSIONS.map((dimension, index) => ({
        ...dimension,
        score: dimensionScore(candidate.id, dimension, index, input),
        rationale: `${dimension.label}由已选品类、人群、市场、价格带、IP 策略和经营目标的固定规则计算；自由文本不加分。`,
        evidence_ids: ["E-INPUT", "E-RULES"],
      }));
      const totalScore = round(dimensions.reduce((sum, item) => sum + item.score * item.weight, 0));
      return {
        concept_id: candidate.id,
        dimensions,
        total_score: totalScore,
        recommendation: blocking ? "NO_GO" : totalScore >= 82 ? "GO" : totalScore >= 72 ? "CONDITIONAL_GO" : "NO_GO",
        evidence_ids: ["E-INPUT", "E-RULES"],
        blocking_risks: blocking ? [blocking] : [],
      };
    });
  }
  function scoreByKey(card, key) {
    return Number(card.dimensions.find((item) => item.key === key)?.score || 0);
  }
  function buildValidation(candidates, scorecards) {
    const byCandidate = {};
    for (const candidate of candidates) {
      const card = scorecards.find((item) => item.concept_id === candidate.id);
      const acceptance = round(clamp(card.total_score / 100, 0.52, 0.90), 2);
      const nps = Math.round((acceptance - 0.62) * 100);
      byCandidate[candidate.id] = {
        concept_id: candidate.id,
        interviews: [{
          persona_name: "任务导向用户镜像",
          segment: candidate.target_segment,
          verdict: acceptance >= 0.78 ? "would_buy" : "needs_revision",
          acceptance,
          objections: ["价格与核心功能的对应关系仍需真实样件验证"],
          must_fixes: ["用真实用户任务测试替换浏览器端模拟接受度"],
          evidence_ids: ["E-SIMULATION"],
        }],
        nps: {
          score: nps,
          rationale: "由固定规则生成的离线推演值，不是问卷或真实访谈结果。",
          evidence_ids: ["E-SIMULATION"],
        },
        average_acceptance: acceptance,
        mode: "offline_pages_deterministic",
      };
    }
    return byCandidate;
  }
  function buildQuality(input, candidates, scorecards) {
    const byCandidate = {};
    const ipRisk = highIpRisk(input);
    const pathRisks = {
      "C-VOC": {
        area: "需求代表性",
        description: "浏览器规则不能验证目标人群需求的真实规模与支付意愿。",
        severity: "medium",
        mitigation: "以 5-8 个真实任务访谈和小批量转化数据校准。",
      },
      "C-TREND": {
        area: "趋势衰减",
        description: "限定主题可能在供应链交付前失去热度。",
        severity: "medium",
        mitigation: "把趋势表达放在可替换内容层，并设置停止补货阈值。",
      },
      "C-WHITESPACE": {
        area: "使用教育",
        description: "模块组合需要额外陈列与用户教育，可能提高首购理解成本。",
        severity: "medium",
        mitigation: "用一眼可懂的基础套装先测，再开放扩展模块。",
      },
    };
    for (const candidate of candidates) {
      const card = scorecards.find((item) => item.concept_id === candidate.id);
      const risks = ipRisk ? [ipRisk, pathRisks[candidate.id]] : [pathRisks[candidate.id]];
      byCandidate[candidate.id] = {
        concept_id: candidate.id,
        overall: ipRisk ? "阻断" : card.total_score >= 82 ? "可小批量验证" : "需补充验证",
        gross_margin_score: scoreByKey(card, "margin_potential"),
        supply_feasibility_score: scoreByKey(card, "supply_feasibility"),
        ip_compliance_score: scoreByKey(card, "ip_compliance"),
        localization_score: scoreByKey(card, "localization_fit"),
        gross_margin: "仅为规则评分，未接入成本或毛利数据",
        supply_chain: "仅为规则评分，未接入供应商与交期数据",
        ip_authorization: IP_LABELS[input.ip_strategy],
        localization: `${MARKET_LABELS[input.target_market]}表达需由区域团队复核`,
        risks,
        evidence_ids: ["E-INPUT", "E-RULES"],
      };
    }
    return byCandidate;
  }
  function buildTrendSignals(input) {
    const category = categoryLabel(input);
    const objectiveSignals = input.objectives.slice(0, 2).map((objective) => ({
      name: OBJECTIVE_LABELS[objective],
      direction: "hypothesis",
      summary: `${OBJECTIVE_LABELS[objective]}是本轮由用户选择的经营目标，仅作为待验证假设，不代表外部趋势事实。`,
      evidence_ids: ["E-INPUT"],
    }));
    return [
      ...objectiveSignals,
      {
        name: `${MARKET_LABELS[input.target_market]}${category}机会`,
        direction: "hypothesis",
        summary: "候选方向由结构化输入映射生成，需用公开趋势资料、门店数据与真实用户研究校验。",
        evidence_ids: ["E-RULES"],
      },
    ];
  }
  function buildOpportunities(input) {
    const category = categoryLabel(input);
    const segment = SEGMENT_LABELS[input.target_segment];
    return [
      {
        id: "OPP-TASK",
        aspect: "高频任务",
        statement: `${segment}在${category}核心任务中的未满足点，可作为样件访谈的第一优先级。`,
        opportunity_score: 8.2,
        impact_score: 8,
        rationale: "由目标人群与品类的结构化选择映射，不是统计结论。",
        evidence_ids: ["E-INPUT", "E-RULES"],
      },
      {
        id: "OPP-PORTFOLIO",
        aspect: "组合复购",
        statement: `围绕${PRICE_LABELS[input.price_band]}价格带测试基础款与扩展模块，验证单品之外的组合空间。`,
        opportunity_score: 7.8,
        impact_score: 7,
        rationale: "固定规则提出的待验证机会。",
        evidence_ids: ["E-RULES"],
      },
    ];
  }
  function buildEvidenceIndex(input) {
    return {
      "E-INPUT": {
        source_id: "E-INPUT",
        source_type: "user_input",
        brand: "MINISO",
        product: categoryLabel(input),
        rating: null,
        text: `本轮结构化输入：${SEGMENT_LABELS[input.target_segment]}、${MARKET_LABELS[input.target_market]}、${PRICE_LABELS[input.price_band]}、${IP_LABELS[input.ip_strategy]}。`,
        date: "2026-07-20",
        url: null,
        data_provenance: "browser_input",
        is_demo: true,
      },
      "E-RULES": {
        source_id: "E-RULES",
        source_type: "deterministic_rule",
        brand: "Trend2SKU",
        product: "Pages 演示规则",
        rating: null,
        text: "仅使用浏览器内固定映射和八维权重生成候选；自由文本不参与加分。",
        date: "2026-07-20",
        url: null,
        data_provenance: "offline_pages",
        is_demo: true,
      },
      "E-SIMULATION": {
        source_id: "E-SIMULATION",
        source_type: "simulation",
        brand: "Trend2SKU",
        product: "离线模拟验证",
        rating: null,
        text: "接受度与 NPS 是确定性演示值，不来自真实访谈、问卷或交易。",
        date: "2026-07-20",
        url: null,
        data_provenance: "offline_pages",
        is_demo: true,
      },
    };
  }
  function buildDemoView(rawInput, threadId, runId) {
    const input = normalizeInput(rawInput);
    const candidates = buildCandidates(input);
    const scorecards = buildScorecards(input, candidates);
    const winnerScorecard = [...scorecards]
      .sort((a, b) => b.total_score - a.total_score || a.concept_id.localeCompare(b.concept_id))[0];
    const winner = candidates.find((item) => item.id === winnerScorecard.concept_id);
    const validation = buildValidation(candidates, scorecards);
    const quality = buildQuality(input, candidates, scorecards);
    const ipBlocked = input.ip_strategy === "evaluate";
    const verdict = ipBlocked ? "NO_GO" : winnerScorecard.recommendation;
    return {
      schema_version: "1.0",
      product: "Trend2SKU",
      run_id: text(runId, 128),
      thread_id: text(threadId, 64),
      status: "completed",
      awaiting_human: false,
      elapsed_seconds: 0.18,
      provider: "offline-pages",
      configured_provider: "offline-pages",
      effective_provider: "offline-pages",
      model: "offline-pages-deterministic",
      category: input.product_category,
      target_brand: "MINISO",
      decision_input: input,
      data_provenance: {
        review_scope: "browser_deterministic_demo",
        review_count: 0,
        official_trend_cutoff: null,
        official_trend_sources: [],
        disclaimer: DATA_BOUNDARY,
      },
      candidate_skus: candidates,
      scorecards,
      winner_scorecard: winnerScorecard,
      portfolio_decision: {
        winner_id: winner.id,
        winner_name: winner.name,
        verdict,
        confidence: ipBlocked ? 0.45 : round(winnerScorecard.total_score / 100, 2),
        rationale: ipBlocked
          ? `${winner.name}规则得分居首，但 IP/合规闸口未关闭，当前建议暂缓。`
          : `${winner.name}在当前结构化条件下的八维加权得分最高，建议先做真实样件验证。`,
        conditions: ipBlocked
          ? ["完成 IP 权属与授权边界审查后重新运行决策"]
          : ["用真实成本、交期、门店和用户数据替换演示参数"],
        evidence_ids: ["E-INPUT", "E-RULES"],
        prfaq: {
          headline: `${winner.name}小批量验证提案`,
          subheading: `${SEGMENT_LABELS[input.target_segment]} · ${MARKET_LABELS[input.target_market]} · ${PRICE_LABELS[input.price_band]}价格带`,
          summary: `本提案依据本轮结构化输入生成。核心动作是先验证${winner.value_proposition}，不把模拟评分解释为销量预测。`,
          call_to_action: ipBlocked ? "先关闭 IP/合规闸口" : "启动样件、任务访谈与门店小样测试",
          external_faq: [
            { question: "这是线上模型生成的结论吗？", answer: "不是。GitHub Pages 版本仅运行浏览器端固定规则。" },
          ],
          internal_faq: [
            { question: "进入立项前还缺什么？", answer: "真实成本、供应链交期、用户任务、门店转化和合规信息。" },
          ],
        },
      },
      trend_signals: buildTrendSignals(input),
      consumer_insights: {
        review_count: 0,
        opportunities: buildOpportunities(input),
        white_space: ["模块化组合与区域内容层分离"],
      },
      launch_validation: {
        by_candidate: validation,
        winner_id: winner.id,
        winner: validation[winner.id],
        disclaimer: "浏览器端模拟验证，不是用户访谈或问卷。",
      },
      quality_audit: {
        by_candidate: quality,
        winner_assessment: quality[winner.id],
        rubric: {
          groundedness: 1,
          faithfulness: 1,
          citation_hit_rate: 1,
          opportunity_coverage: 0.65,
          persona_fidelity: 0.55,
          explainability: 1,
          overall: 0.82,
        },
        evidence_count: 3,
        claim_count: 0,
        mode: "offline_pages_deterministic",
      },
      evidence_index: buildEvidenceIndex(input),
      audit: {
        tool_calls: [{ tool_name: "load_browser_demo_rules", status: "success", used_fallback: false }],
        trace: [],
        experience_baseline: {
          arm_a: { opportunity_coverage: 0.2, evidence_citations: 0, nps_prediction: 0 },
          arm_b: { opportunity_coverage: 0.65, evidence_citations: 3, nps_prediction: 0 },
          deltas: { opportunity_coverage: 0.45, evidence_citations: 3, nps_prediction: 0 },
          narrative: "仅演示 Agent 决策结构与经验基线的字段差异，不构成真实效果实验。",
        },
      },
    };
  }
  function randomHex(byteLength) {
    const bytes = new Uint8Array(byteLength);
    if (root.crypto && typeof root.crypto.getRandomValues === "function") {
      root.crypto.getRandomValues(bytes);
    } else {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = Math.floor(Math.random() * 256);
      }
    }
    return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
  }
  function reportMarkdown(view, kind = "full") {
    const input = view.decision_input;
    const winner = view.candidate_skus.find((item) => item.id === view.portfolio_decision.winner_id);
    const boundary = `> 数据边界：${DATA_BOUNDARY}`;
    if (kind === "opening") {
      return [
        "# Trend2SKU 开题报告摘要",
        "",
        boundary,
        "",
        "## 研究问题",
        `如何把“${text(input.brief, 160)}”转化为可比较、可追溯、可验证的候选 SKU 组合。`,
        "",
        "## 演示方法",
        "浏览器根据品类、人群、市场、价格带、IP 策略和经营目标生成三条候选路径，并按八维固定权重评分。",
        "",
        "## 下一步",
        "接入真实用户任务、成本、交期、门店转化和合规资料，重新校准评分与闸口。",
        "",
        `运行记录：${view.run_id}`,
      ].join("\n");
    }
    const candidateRows = view.scorecards.map((card) => {
      const candidate = view.candidate_skus.find((item) => item.id === card.concept_id);
      return `| ${card.concept_id} | ${candidate.name} | ${card.total_score.toFixed(2)} | ${card.recommendation} |`;
    }).join("\n");
    const highRisks = view.quality_audit.by_candidate[winner.id].risks
      .filter((risk) => risk.severity === "high")
      .map((risk) => `- **${risk.area}**：${risk.description} 缓解动作：${risk.mitigation}`);
    return [
      "# Trend2SKU GitHub Pages 离线交互演示",
      "",
      boundary,
      "",
      `- 运行记录：${view.run_id}`,
      `- 决策简报：${text(input.brief, 200)}`,
      `- 商品品类：${categoryLabel(input)}`,
      `- 目标人群：${SEGMENT_LABELS[input.target_segment]}`,
      `- 目标市场：${MARKET_LABELS[input.target_market]}`,
      `- 价格带：${PRICE_LABELS[input.price_band]}`,
      `- IP 策略：${IP_LABELS[input.ip_strategy]}`,
      `- 经营目标：${input.objectives.map((item) => OBJECTIVE_LABELS[item]).join("、")}`,
      "",
      "## 候选组合",
      "",
      "| ID | 候选 SKU | 八维加权分 | 建议 |",
      "| --- | --- | ---: | --- |",
      candidateRows,
      "",
      "## 组合决策",
      `**${view.portfolio_decision.verdict}：${winner.name}**`,
      "",
      view.portfolio_decision.rationale,
      "",
      "## 阻断风险",
      ...(highRisks.length ? highRisks : ["- 当前没有固定规则识别出的高严重度阻断项；仍需真实数据校准。"]),
      "",
      "## 建议验证动作",
      ...view.portfolio_decision.conditions.map((item) => `- ${item}`),
      "- 通过真实样件任务访谈和门店小样测试验证购买与复购假设。",
    ].join("\n");
  }
  function createDemoEngine(options = {}) {
    const tickets = new Map();
    const reports = new Map();
    const makeHex = typeof options.randomHex === "function" ? options.randomHex : randomHex;
    function issueTicket(rawInput, threadId) {
      let token = "";
      for (let attempt = 0; attempt < 5; attempt += 1) {
        token = String(makeHex(16)).toLowerCase();
        if (/^[a-f0-9]{32}$/.test(token) && !tickets.has(token)) break;
      }
      if (!/^[a-f0-9]{32}$/.test(token) || tickets.has(token)) {
        throw new Error("无法生成一次性运行票据");
      }
      const normalizedThreadId = text(threadId, 64);
      if (!/^[A-Za-z0-9_-]+$/.test(normalizedThreadId)) {
        throw new Error("thread_id 不符合契约");
      }
      tickets.set(token, { input: normalizeInput(rawInput), threadId: normalizedThreadId });
      return { thread_id: normalizedThreadId, stream_url: `api/stream?ticket=${token}` };
    }
    function consumeTicket(streamUrl) {
      const match = /^api\/stream\?ticket=([a-f0-9]{32})$/.exec(String(streamUrl));
      if (!match || !tickets.has(match[1])) throw new Error("运行票据无效或已使用");
      const record = tickets.get(match[1]);
      tickets.delete(match[1]);
      const runId = `run-pages-${String(makeHex(12)).toLowerCase()}`;
      if (!/^run-pages-[a-f0-9]{24}$/.test(runId)) throw new Error("run_id 生成失败");
      const view = buildDemoView(record.input, record.threadId, runId);
      const envelope = (payload) => ({ run_id: runId, thread_id: record.threadId, ...payload });
      const events = [];
      for (const node of STAGES) {
        events.push(envelope({ type: "trace", event: { node, kind: "start", status: "success" } }));
        events.push(envelope({ type: "trace", event: { node, kind: "end", status: "success" } }));
      }
      events.push(envelope({ type: "result", view }));
      events.push(envelope({ type: "done" }));
      reports.set(runId, view);
      return { view, events };
    }
    function report(runId, kind) {
      const view = reports.get(String(runId));
      return view ? reportMarkdown(view, kind === "opening" ? "opening" : "full") : null;
    }
    return { issueTicket, consumeTicket, report };
  }
  function shouldEnablePagesDemo(locationLike = {}) {
    const hostname = String(locationLike.hostname || "").toLowerCase();
    const queryEnabled = new URLSearchParams(String(locationLike.search || "")).get("pages_demo") === "1";
    return hostname === "github.io" || hostname.endsWith(".github.io") || queryEnabled;
  }
  function installPagesDemo(target = root) {
    if (!target || target.__TREND2SKU_PAGES_DEMO_INSTALLED__) {
      return target?.Trend2SKUPagesDemoEngine || null;
    }
    const engine = createDemoEngine();
    const nativeFetch = typeof target.fetch === "function" ? target.fetch.bind(target) : null;
    const routeFrom = (request) => {
      const raw = typeof request === "string" || request instanceof target.URL
        ? String(request)
        : String(request?.url || "");
      const url = new target.URL(raw, target.location?.href || "https://pages.invalid/");
      const marker = url.pathname.lastIndexOf("/api/");
      return { url, route: marker >= 0 ? url.pathname.slice(marker + 1) : "" };
    };
    const jsonResponse = (payload, status = 200) => new target.Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
    target.fetch = async (request, init = {}) => {
      const { url, route } = routeFrom(request);
      if (route === "api/health") {
        return jsonResponse({
          status: "ok",
          product: "Trend2SKU",
          schema_version: "1.0",
          provider: "offline-pages",
          configured_provider: "offline-pages",
          effective_provider: "offline-pages",
          model: "offline-pages-deterministic",
        });
      }
      if (route === "api/stream/ticket") {
        const method = String(init.method || request?.method || "GET").toUpperCase();
        if (method !== "POST") return jsonResponse({ detail: "Method Not Allowed" }, 405);
        let rawBody = init.body;
        if (rawBody == null && typeof request?.clone === "function") rawBody = await request.clone().text();
        try {
          const body = JSON.parse(String(rawBody || "{}"));
          return jsonResponse(engine.issueTicket(body, body.thread_id));
        } catch (error) {
          return jsonResponse({ detail: text(error?.message || "Invalid request", 160) }, 422);
        }
      }
      if (route === "api/report") {
        const markdown = engine.report(url.searchParams.get("run_id"), url.searchParams.get("kind"));
        return markdown == null
          ? jsonResponse({ detail: "Report not found" }, 404)
          : jsonResponse({ markdown });
      }
      if (route.startsWith("api/")) return jsonResponse({ detail: "Not found" }, 404);
      if (!nativeFetch) throw new TypeError("Fetch is unavailable");
      return nativeFetch(request, init);
    };
    class PagesEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      constructor(url) {
        this.url = String(url);
        this.readyState = PagesEventSource.CONNECTING;
        this.withCredentials = false;
        this.onopen = null;
        this.onmessage = null;
        this.onerror = null;
        this._closed = false;
        this._listeners = new Map();
        let stream;
        try {
          stream = engine.consumeTicket(this.url);
        } catch (error) {
          target.setTimeout(() => {
            if (this._closed) return;
            this.readyState = PagesEventSource.CLOSED;
            this._dispatch("error", { type: "error", error });
          }, 0);
          return;
        }
        target.setTimeout(() => {
          if (this._closed) return;
          this.readyState = PagesEventSource.OPEN;
          this._dispatch("open", { type: "open" });
        }, 0);
        stream.events.forEach((event, index) => {
          target.setTimeout(() => {
            if (this._closed) return;
            this._dispatch("message", { type: "message", data: JSON.stringify(event) });
            if (event.type === "done") this.readyState = PagesEventSource.CLOSED;
          }, 8 * (index + 1));
        });
      }
      addEventListener(type, listener) {
        if (typeof listener !== "function") return;
        const listeners = this._listeners.get(type) || new Set();
        listeners.add(listener);
        this._listeners.set(type, listeners);
      }
      removeEventListener(type, listener) {
        this._listeners.get(type)?.delete(listener);
      }
      _dispatch(type, event) {
        const handler = this[`on${type}`];
        if (typeof handler === "function") handler.call(this, event);
        for (const listener of this._listeners.get(type) || []) listener.call(this, event);
      }
      close() {
        this._closed = true;
        this.readyState = PagesEventSource.CLOSED;
      }
    }
    PagesEventSource.prototype.CONNECTING = PagesEventSource.CONNECTING;
    PagesEventSource.prototype.OPEN = PagesEventSource.OPEN;
    PagesEventSource.prototype.CLOSED = PagesEventSource.CLOSED;
    target.EventSource = PagesEventSource;
    target.__TREND2SKU_PAGES_DEMO_INSTALLED__ = true;
    target.Trend2SKUPagesDemoEngine = engine;
    if (target.document?.documentElement) {
      target.document.documentElement.dataset.runtime = "offline-pages";
    }
    return engine;
  }

  const publicApi = {
    DATA_BOUNDARY,
    DIMENSIONS,
    normalizeInput,
    stableHash,
    buildDemoView,
    reportMarkdown,
    createDemoEngine,
    shouldEnablePagesDemo,
    installPagesDemo,
  };
  if (moduleLike) moduleLike.exports = publicApi;
  if (root.window) {
    root.window.Trend2SKUPagesDemo = publicApi;
    if (shouldEnablePagesDemo(root.window.location)) installPagesDemo(root.window);
  }
  return publicApi;
})(globalThis, typeof module !== "undefined" && module.exports ? module : null);
