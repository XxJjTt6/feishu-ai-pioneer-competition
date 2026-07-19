# Dynamic Decision Workbench and Qwen3.7 Plus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a user-configurable Trend2SKU workbench whose structured inputs change candidates, validation, scores, and reports, while all remote LLM narration uses Alibaba Cloud Coding Plan `qwen3.7-plus` through its OpenAI-compatible endpoint.

**Architecture:** Add a normalized `DecisionInput` contract at the API/application boundary and persist it in `PipelineState`. A focused candidate-profile module converts that input into three auditable paths without allowing user keywords to directly alter scores. Extend the provider-agnostic LLM gateway with a Qwen client, and replace the fixed frontend brief with a validated form, dynamic result controls, report dialog, and downloads.

**Tech Stack:** Python 3.10+, Pydantic 2, FastAPI, requests, vanilla HTML/CSS/JavaScript, SSE, pytest, headless Chrome.

---

### Task 1: DecisionInput Contract

**Files:**
- Create: `backend/miniso_studio/common/decision_input.py`
- Modify: `backend/miniso_studio/application/graph/state.py`
- Modify: `backend/miniso_studio/application/runner.py`
- Test: `backend/tests/test_dynamic_decision_input.py`

- [ ] **Step 1: Write failing validation and normalization tests**

```python
def test_decision_input_requires_custom_category_for_other():
    with pytest.raises(ValidationError):
        DecisionInput(brief="设计新品", product_category="other", custom_category="")

def test_decision_input_normalizes_objectives_without_duplicates():
    value = DecisionInput(brief="设计新品", objectives=["social", "margin", "social"])
    assert value.objectives == ["social", "margin"]
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dynamic_decision_input.py -q`

Expected: FAIL because `miniso_studio.common.decision_input` does not exist.

- [ ] **Step 3: Implement the contract**

```python
class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief: str = Field(min_length=1, max_length=500)
    product_category: ProductCategory = "fragrance_accessory"
    custom_category: str = Field(default="", max_length=40)
    target_segment: TargetSegment = "young_professional"
    target_market: TargetMarket = "global"
    price_band: PriceBand = "mid"
    ip_strategy: IPStrategy = "original"
    objectives: list[Objective] = Field(default_factory=lambda: ["emotional", "social"])
    constraints: str = Field(default="", max_length=300)
```

Add validators for whitespace, `other`, 1-4 unique objectives, and a `category_label` property. Add `decision_input: DecisionInput` to `PipelineState`; update `run_studio()` and initial-state creation to accept either a `DecisionInput` or legacy `brief` and create a normalized default.

- [ ] **Step 4: Verify GREEN and legacy compatibility**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dynamic_decision_input.py backend/tests/test_smoke.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/miniso_studio/common/decision_input.py backend/miniso_studio/application/graph/state.py backend/miniso_studio/application/runner.py backend/tests/test_dynamic_decision_input.py
git commit -m "feat: add structured decision input"
```

### Task 2: Dynamic Three-Path Candidate Portfolio

**Files:**
- Create: `backend/miniso_studio/application/portfolio/dynamic_candidates.py`
- Create: `backend/miniso_studio/application/portfolio/__init__.py`
- Modify: `backend/miniso_studio/application/agents/product_manager.py`
- Modify: `backend/miniso_studio/application/agents/user_proxy.py`
- Modify: `backend/miniso_studio/application/agents/industry_expert.py`
- Test: `backend/tests/test_dynamic_decision_input.py`

- [ ] **Step 1: Write failing variation tests**

```python
def test_two_decision_inputs_change_candidates_and_validation():
    plush = run_studio(decision_input=DecisionInput(brief="做礼赠新品", product_category="plush", target_segment="family"))
    stationery = run_studio(decision_input=DecisionInput(brief="做开学新品", product_category="stationery", target_segment="student"))
    assert {item.name for item in plush.state.concepts} != {item.name for item in stationery.state.concepts}
    assert plush.state.candidate_evaluations["C-VOC"].interviews[0].transcript != stationery.state.candidate_evaluations["C-VOC"].interviews[0].transcript
```

- [ ] **Step 2: Verify RED**

Run the new test and confirm both runs currently return the same fixed names.

- [ ] **Step 3: Implement profile-driven candidates**

Create immutable category profiles containing a noun, physical form, functional modules, material risks, and scenario vocabulary. Implement:

```python
def build_dynamic_portfolio(
    decision: DecisionInput,
    opportunities: list[Opportunity],
    trends: list[TrendSignal],
) -> list[ProductConcept]:
    """Return C-VOC, C-TREND and C-WHITESPACE in stable order."""
```

Candidate copy must include normalized segment, market, price and IP strategy. Pass `decision_input` into user-mirror questions and merchandise-risk context. Do not add score bonuses based directly on objectives or brief text.

- [ ] **Step 4: Verify GREEN and stable IDs**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dynamic_decision_input.py backend/tests/test_agent_tools.py backend/tests/test_scorecard.py -q`

Expected: dynamic variation passes; IDs remain exactly `C-VOC`, `C-TREND`, `C-WHITESPACE`; all score weights total 1.0.

- [ ] **Step 5: Commit**

```bash
git add backend/miniso_studio/application/portfolio backend/miniso_studio/application/agents backend/tests/test_dynamic_decision_input.py
git commit -m "feat: generate portfolio from decision inputs"
```

### Task 3: API, SSE and Report Input Snapshot

**Files:**
- Modify: `backend/miniso_studio/starter/api.py`
- Modify: `backend/miniso_studio/application/reporting.py`
- Test: `backend/tests/test_api_contract.py`
- Test: `backend/tests/test_dynamic_decision_input.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_api_echoes_normalized_decision_input_and_changes_results(client):
    payload = {"brief":"设计开学礼赠", "product_category":"stationery", "target_segment":"student", "target_market":"china", "price_band":"entry", "ip_strategy":"original", "objectives":["social","margin"]}
    view = client.post("/api/run", json=payload).json()
    assert view["decision_input"] == payload | {"custom_category":"", "constraints":""}
    assert "文具" in " ".join(item["name"] for item in view["candidate_skus"])
```

Add SSE coverage for the same query fields and 422 cases for unknown enums, too many objectives and missing custom category.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dynamic_decision_input.py -q`

Expected: FAIL because request models and views lack the new fields.

- [ ] **Step 3: Implement API propagation**

Make `RunRequest` inherit the shared input fields or build `DecisionInput` explicitly. Add equivalent typed Query parameters to `/api/stream`. Include `decision_input.model_dump(mode="json")` in `to_view()`, and add a “本轮决策输入” section to full/opening reports.

- [ ] **Step 4: Verify GREEN**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_dynamic_decision_input.py backend/tests/test_api_contract.py -q`

Expected: all API and SSE tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/miniso_studio/starter/api.py backend/miniso_studio/application/reporting.py backend/tests
git commit -m "feat: expose dynamic decision input through api"
```

### Task 4: Qwen3.7 Plus Provider

**Files:**
- Create: `backend/miniso_studio/infrastructure/llm/qwen.py`
- Modify: `backend/miniso_studio/common/config.py`
- Modify: `backend/miniso_studio/infrastructure/llm/gateway.py`
- Modify: `.env.example`
- Test: `backend/tests/test_qwen_provider.py`

- [ ] **Step 1: Write failing client and provider tests**

```python
def test_qwen_client_uses_openai_contract(monkeypatch):
    captured = {}
    monkeypatch.setattr(requests, "post", fake_qwen_response(captured))
    response = QwenClient("secret", "https://coding.dashscope.aliyuncs.com/v1", "qwen3.7-plus").chat("system", "prompt")
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "qwen3.7-plus"
    assert captured["json"]["enable_thinking"] is False
    assert response.provider == "qwen"
```

Add tests for missing-key fallback, safe HTTP errors, usage parsing and settings loaded from Qwen variables.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_qwen_provider.py -q`

Expected: FAIL because Qwen provider files and settings do not exist.

- [ ] **Step 3: Implement Qwen client and generic remote gateway**

Implement `QwenClient.chat()` using `requests.post(..., json=payload, timeout=90)`. Parse `choices[0].message.content`, usage tokens and `x-request-id`. Errors may include status and request ID only. Refactor `LLMGateway` to store `_remote`, while accepting legacy `minimax_client` in tests. Add `provider_status()` and `from_settings()` support for `qwen`.

- [ ] **Step 4: Create local secret configuration**

Create untracked `.env` with `MINISO_LLM_PROVIDER=qwen`, `QWEN_BASE_URL=https://coding.dashscope.aliyuncs.com/v1`, `QWEN_MODEL=qwen3.7-plus`, `QWEN_ENABLE_THINKING=false`, and the user-supplied Key. Set mode `0600`; verify `git check-ignore .env` succeeds and no tracked file contains the Key.

- [ ] **Step 5: Verify GREEN without exposing the Key**

Run unit tests, then call the provider through a script that prints only provider, model, non-empty text boolean, token counts and request ID. Never print environment values, headers or raw errors.

- [ ] **Step 6: Commit code without `.env`**

```bash
git add backend/miniso_studio/infrastructure/llm backend/miniso_studio/common/config.py backend/tests/test_qwen_provider.py .env.example
git commit -m "feat: use qwen3.7 plus for remote narration"
```

### Task 5: Dynamic Frontend Controls and Actions

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `backend/tests/test_frontend_copy.py`

- [ ] **Step 1: Write failing DOM and browser tests**

Tests must assert: no `value=` on `#brief`; run disabled on load; required selections enable run; captured EventSource URL contains every normalized field; clear resets form and results; two runs use new thread IDs; candidate buttons update the controlled panel; report buttons fetch the correct run; download creates a blob with expected filename.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_frontend_copy.py -q`

Expected: failures for missing controls, report dialog and actions.

- [ ] **Step 3: Implement the form and request model**

Add semantic labels and controls for all `DecisionInput` fields. Implement pure functions:

```javascript
function readDecisionInput(form) { /* normalized object */ }
function validateDecisionInput(input) { /* {valid, errors} */ }
function buildStreamUrl(input, threadId) { /* URLSearchParams */ }
```

Use checkboxes for objectives, selects for controlled fields, a conditional custom-category input, character counters, an icon clear button with tooltip, and stable responsive dimensions.

- [ ] **Step 4: Implement report dialog and downloads**

Use a native `<dialog>` with close icon, report tabs, retry state and a `<pre>` text surface. Fetch `api/report?run_id=...&kind=...`, render `markdown` with `textContent`, and download via an object URL. Add JSON download from the validated in-memory view.

- [ ] **Step 5: Verify GREEN at all breakpoints**

Run frontend tests, `node --check frontend/app.js`, and browser checks at 375x812, 390x844, 1121x800 and 1440x900. Confirm no page overflow, overlapping controls, console errors or blank images.

- [ ] **Step 6: Commit**

```bash
git add frontend backend/tests/test_frontend_copy.py
git commit -m "feat: make decision workbench fully interactive"
```

### Task 6: Documentation, Packaging and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/迁移说明.md`
- Modify: `scripts/package_submission_v1.py`
- Create: `deliverables/提交清单_v2.md`

- [ ] **Step 1: Update user documentation**

Document the dynamic fields, Qwen/OpenAI-compatible configuration, safe offline fallback, Coding Plan endpoint, and explicit rule that `.env` never enters the package. Do not include the Key.

- [ ] **Step 2: Run full source verification**

Run all pytest tests, pre-PR, Node syntax, Python compileall, dynamic CLI inputs, synchronous API, SSE and live Qwen provider smoke test with sanitized output.

- [ ] **Step 3: Generate a fresh versioned output directory**

Use a new `outputs-trend2sku-v3` directory. Package from the positive allowlist, copy updated documents and screenshots, write a new checklist, and refuse overwrites.

- [ ] **Step 4: Verify extracted ZIP**

Extract into a fresh verification directory; validate the single ZIP top-level, 100% MANIFEST match, ZIP CRC, external SHA, full pytest, CLI/API/SSE, and absence of `.env`, Key prefix, emails, local paths, public IPs, caches and legacy artifacts.

- [ ] **Step 5: Start final service**

Stop only the earlier v1 server process, then start v2 on port 8767. Health must report `configured_provider=qwen`, `effective_provider=qwen` and the final browser run must show `qwen3.7-plus`; otherwise report the real fallback state.

- [ ] **Step 6: Commit final non-secret files**

```bash
git add README.md docs scripts deliverables/提交清单_v2.md
git commit -m "docs: finalize dynamic qwen submission"
```
