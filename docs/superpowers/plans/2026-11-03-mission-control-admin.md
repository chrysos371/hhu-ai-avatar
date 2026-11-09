# Mission Control Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-file memory workbench with a React Mission Control that safely manages persona, emotion, memory, knowledge, reminders, tools and audited natural-language operations.

**Architecture:** A Vite React/TypeScript SPA calls versioned Python REST endpoints. Python owns all validation, draft/confirm state transitions, SQLite transactions and audit events; the SPA never writes state without a confirmed server-side draft. Production Python serves `frontend/dist`, while existing `/api/*` endpoints remain compatible during migration.

**Tech Stack:** Python 3.10+, standard-library HTTP/SQLite backend, React, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS, Recharts, Lucide, Vitest, Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-03-mission-control-admin-design.md`

## 2026-11-10 实施与验收记录

以下交付表为当前进度；后面的原始步骤保留为设计时的工作清单，未逐条改写为实际命令历史。

- [x] Task 1：React 应用壳、安全静态托管、缺失构建指引。
- [x] Task 2：共享 SQLite 迁移、v1 统一信封与安全门禁。
- [x] Task 3：十分钟草案、一次性令牌、基线冲突与原子审计。
- [x] Task 4：真实总览、对话 trace、提醒管理与兼容迁移。
- [x] Task 5：人设版本、实际提示词消费、本地试聊、管理 Agent 仅建议草案。
- [x] Task 6：定时情绪表达覆盖、记忆来源/历史/筛选/批量草案。
- [x] Task 7：UTF-8 文件上传、固定预览切片、独立知识检索与引用。
- [x] Task 8：工具健康、审计详情与反向草案、浏览器确认流程。
- [x] Task 9：正式关闭旧直写入口、保留兼容开关、运行文档与验证。

实际组织有所调整：领域服务与事务引擎先一起提交，再提交 API/Avatar 集成，最后提交完整页面，避免提交不可导入的中间依赖。Task 3/4/5/6/7 的部分 Python 场景合并在 `test_admin_domains.py`、`test_web_api_v1.py`；四个核心浏览器流程合并为 `frontend/e2e/admin.spec.ts`，并增加全路由刷新与真实规则回退对话检查。必需的 superpowers 执行技能在本机不可用，按计划手工执行实现与验证；没有派生子代理。

范围与限制：未调用云端生成数据、未训练模型。通用语义 Verifier 尚未配置，界面如实显示不可用；现有字面交付检查不能替代它。向量去重有明确处理上限，服务失败回退词面；确认固定使用草案内已预览切片。旧只读 API 保留，正式启动关闭旧 POST；库函数兼容开关见运行文档。没有推送远程。

最终验证：工作区 Python 全量 **533 passed**，前端组件 **18 passed**，Playwright **5 passed**；独立已提交代码副本 Python **467 passed**；lint、TypeScript、生产构建与真实 CLI 临时库启动检查通过。桌面与 390px 窄屏已查看，未发现横向溢出或页面异常。

运行方法与数据/备份说明见 [Mission Control 后台](../../Mission-Control后台.md)。

## Global Constraints

- Bind only to `127.0.0.1`; preserve random token, exact Host/Origin checks, CSP, `no-store`, request-size validation and single-user warning.
- Every persona, emotion, knowledge or batch mutation follows draft → field-level diff → explicit confirmation → atomic execution → audit.
- Natural-language management uses the local model by default; cloud use requires an explicit per-request choice and never occurs as automatic fallback.
- Knowledge input is UTF-8 `.txt`/`.md`, maximum 5 MiB per file; knowledge remains separate from user memory.
- Frontend renders untrusted text as text, never `innerHTML`; APIs never expose credentials, `.env`, vectors or tracebacks.
- Existing `/api/*` behavior remains available until the replacement UI and `/api/v1/*` paths pass parity tests.
- Training-data generation and model training are out of scope.
- Each task uses TDD and ends with a focused commit; full Python and frontend suites run before final delivery.

## Review Focus

- A draft confirmed after its baseline changed must return `409 stale_draft` and perform no write — pinned in Task 3.
- A confirmation token reused, expired or paired with another draft must fail without an audit success event — pinned in Task 3.
- A knowledge upload containing invalid UTF-8, path traversal or more than 5 MiB must be rejected before parsing — pinned in Task 7.
- An audit insert failure must roll back the domain mutation in the same transaction — pinned in Task 3 and each domain task.
- Missing/corrupt `frontend/dist` must produce a clear setup response and must not expose arbitrary files — pinned in Task 1.

---

### Task 1: React application shell and safe production hosting

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/app/AppShell.tsx`
- Create: `frontend/src/styles/index.css`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/app/AppShell.test.tsx`
- Modify: `src/avatar/web.py`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Produces: `frontend/dist/index.html` and hashed assets; Python route `GET /` plus `GET /assets/<safe-name>`; React routes `/`, `/chat`, `/persona`, `/emotion`, `/memory`, `/knowledge`, `/reminders`, `/tools`, `/audit`.
- Produces: `AppShell` with Mission Control sidebar, top health bar, responsive content outlet and persistent single-user-local warning.

- [ ] **Step 1: Write failing backend static-hosting tests**

Add tests named `test_server_serves_spa_and_hashed_assets`, `test_spa_fallback_does_not_shadow_api`, `test_static_path_traversal_is_rejected`, and `test_missing_dist_returns_build_instructions`. Use a temporary fake `dist` passed to `create_server(..., frontend_dir=...)`; assert content types, CSP, `404` for traversal, and no filesystem content leakage.

- [ ] **Step 2: Run backend tests and verify RED**

Run: `python -m pytest tests/test_web_static.py -q`

Expected: FAIL because `create_server` has no `frontend_dir` contract and no asset router.

- [ ] **Step 3: Implement safe static hosting**

Change signature to `create_server(db_path: str, *, port: int = 8765, frontend_dir: str | Path | None = None) -> HTTPServer`. Resolve asset targets below the configured directory, use a fixed content-type map, serve SPA fallback only for non-API GET routes, and return build guidance when `index.html` is absent.

- [ ] **Step 4: Scaffold the frontend and write the failing shell test**

Initialize the exact dependency set from Tech Stack with a lockfile. Test that all navigation labels render, the current route is indicated accessibly, desktop sidebar becomes compact at narrow width, and no invented KPI values are present.

- [ ] **Step 5: Run frontend shell test and verify RED**

Run: `npm --prefix frontend test -- --run src/app/AppShell.test.tsx`

Expected: FAIL before `AppShell` and routes exist.

- [ ] **Step 6: Implement the Mission Control shell**

Use the approved “Mission Control” direction: dark, dense, restrained blue/cyan status accents, left navigation, top service state and a content outlet. Do not implement feature data yet.

- [ ] **Step 7: Verify Task 1**

Run: `npm --prefix frontend run build`

Run: `npm --prefix frontend test -- --run`

Run: `python -m pytest tests/test_web.py tests/test_web_static.py -q`

- [ ] **Step 8: Commit**

```bash
git add frontend src/avatar/web.py tests/test_web_static.py
git commit -m "feat: add Mission Control React shell"
```

### Task 2: Management database and versioned API foundation

**Files:**
- Create: `src/avatar/brain/admin_store.py`
- Create: `src/avatar/web_api.py`
- Modify: `src/avatar/web.py`
- Test: `tests/test_admin_store.py`
- Test: `tests/test_web_api_v1.py`

**Interfaces:**
- Produces: `AdminStore(memory: MemoryStore)` sharing the caller's SQLite connection and transaction boundary.
- Produces: idempotent tables `persona_versions`, `emotion_overrides`, `knowledge_sources`, `knowledge_chunks`, `operation_drafts`, `audit_events`.
- Produces: `GET /api/v1/system`, `GET /api/v1/audit`, and a JSON envelope `{data, error, request_id}`.
- Consumes: existing token/Host/Origin request gate from `web.py`.

- [ ] **Step 1: Write failing migration and reopen tests**

Test first-open creation, second-open idempotence, legacy database upgrade, JSON round-trip, invalid enum/check constraints, and that initial persona is seeded from current config exactly once.

- [ ] **Step 2: Run storage tests and verify RED**

Run: `python -m pytest tests/test_admin_store.py -q`

Expected: FAIL because `AdminStore` does not exist.

- [ ] **Step 3: Implement `AdminStore` schema and read methods**

Required signatures:

```python
class AdminStore:
    def migrate(self, initial_persona: dict[str, object]) -> None: ...
    def current_persona(self) -> dict[str, object]: ...
    def list_audit(self, *, limit: int = 100, before_id: int | None = None) -> list[dict]: ...
    def system_counts(self) -> dict[str, int]: ...
```

Store canonical JSON with deterministic key ordering; reject NaN and unsupported types.

- [ ] **Step 4: Write failing `/api/v1` contract tests**

Assert envelope shape, request ID, authentication, JSON media type, pagination validation, credential redaction and unchanged legacy `/api/state` behavior.

- [ ] **Step 5: Implement the API router split**

Move versioned routing/validation into `web_api.py`; keep network and security headers in `web.py`. Do not copy business SQL into handlers.

- [ ] **Step 6: Verify Task 2**

Run: `python -m pytest tests/test_admin_store.py tests/test_web_api_v1.py tests/test_web.py -q`

- [ ] **Step 7: Commit**

```bash
git add src/avatar/brain/admin_store.py src/avatar/web_api.py src/avatar/web.py tests/test_admin_store.py tests/test_web_api_v1.py
git commit -m "feat: add admin storage and v1 API"
```

### Task 3: Draft, confirmation and audit transaction engine

**Files:**
- Create: `src/avatar/brain/operations.py`
- Modify: `src/avatar/brain/admin_store.py`
- Modify: `src/avatar/web_api.py`
- Test: `tests/test_admin_operations.py`
- Test: `tests/test_web_operation_api.py`

**Interfaces:**
- Produces: `OperationType = Literal['persona.update','emotion.override','knowledge.import','memory.batch']`.
- Produces: `OperationService.create_draft(...)`, `preview(draft_id)`, `confirm(draft_id, token)`, `create_reverse_draft(audit_id)`.
- Produces: `POST /api/v1/operations/draft`, `GET /api/v1/operations/{id}`, `POST /api/v1/operations/{id}/confirm`, `POST /api/v1/audit/{id}/reverse-draft`.
- Consumes: domain executors registered by exact `OperationType`; no executor accepts raw SQL or arbitrary callable names from model output.

- [ ] **Step 1: Write the failing state-machine tests**

Cover `draft → confirmed`, `draft → expired`, stale baseline, wrong token, token reuse, cross-draft token, unsupported operation, malformed parameters, executor failure, audit failure and concurrent double confirmation. Assert a single winning confirmation and zero partial writes.

- [ ] **Step 2: Run operation tests and verify RED**

Run: `python -m pytest tests/test_admin_operations.py -q`

Expected: FAIL because the operation engine does not exist.

- [ ] **Step 3: Implement the operation engine**

Required signatures:

```python
@dataclass(frozen=True)
class OperationPreview:
    draft_id: int
    operation_type: str
    diff: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    expires_at: float
    confirmation_token: str

class OperationService:
    def create_draft(self, operation_type: str, parameters: dict, *, actor: str = "local-admin") -> OperationPreview: ...
    def preview(self, draft_id: int) -> OperationPreview: ...
    def confirm(self, draft_id: int, confirmation_token: str) -> dict: ...
    def create_reverse_draft(self, audit_id: int) -> OperationPreview: ...
```

Hash confirmation tokens at rest. Recheck baseline and expiry inside `BEGIN IMMEDIATE`; execute domain mutation and audit insert in the same transaction.

- [ ] **Step 4: Write and implement API tests**

Assert `201` draft, `200` preview/confirm, `409 stale_draft`, `410 expired_draft`, `422 invalid_operation`, token never appearing in audit, and no confirm endpoint accepting only operation parameters.

- [ ] **Step 5: Verify Task 3**

Run: `python -m pytest tests/test_admin_operations.py tests/test_web_operation_api.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/avatar/brain/operations.py src/avatar/brain/admin_store.py src/avatar/web_api.py tests/test_admin_operations.py tests/test_web_operation_api.py
git commit -m "feat: add confirmed admin operation engine"
```

### Task 4: Dashboard, chat observability and existing-feature migration

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/features/dashboard/DashboardPage.tsx`
- Create: `frontend/src/features/dashboard/DashboardPage.test.tsx`
- Create: `frontend/src/features/chat/ChatPage.tsx`
- Create: `frontend/src/features/chat/ChatPage.test.tsx`
- Create: `frontend/src/features/reminders/RemindersPage.tsx`
- Create: `frontend/src/features/reminders/RemindersPage.test.tsx`
- Modify: `src/avatar/main.py`
- Modify: `src/avatar/web_api.py`
- Test: `tests/test_chat_observability.py`

**Interfaces:**
- Produces: typed `apiRequest<T>(path, options) -> Promise<T>` reading the session token established from the URL fragment.
- Produces: `GET /api/v1/dashboard`, `POST /api/v1/chat`, reminder CRUD paths.
- `POST /api/v1/chat` adds `trace` with recalled memory summaries, decision, tool calls, Guard findings and Verifier issues; secrets and hidden prompts are excluded.

- [ ] **Step 1: Write failing backend observability tests**

Assert successful and repaired replies expose only structured trace fields, failed internal exceptions remain generic, recalled content follows trust rules, and legacy chat response fields remain unchanged.

- [ ] **Step 2: Implement dashboard/chat/reminder v1 endpoints**

Use existing `Avatar.respond`, memory and reminder services. Dashboard metrics must be derived from actual rows/events; unavailable metrics return `null` with a reason, never fabricated numbers.

- [ ] **Step 3: Write failing frontend tests**

Cover dashboard loading/error/empty states, real service health labels, chat bubbles, collapsed trace, repair/guard warnings, disabled submit while pending, and reminder lifecycle.

- [ ] **Step 4: Implement dashboard, chat and reminders pages**

Use TanStack Query for reads/mutations and invalidate exact affected keys. Preserve the approved Mission Control visual hierarchy.

- [ ] **Step 5: Verify Task 4**

Run: `python -m pytest tests/test_chat_observability.py tests/test_web.py -q`

Run: `npm --prefix frontend test -- --run`

- [ ] **Step 6: Commit**

```bash
git add frontend/src src/avatar/main.py src/avatar/web_api.py tests/test_chat_observability.py
git commit -m "feat: add dashboard and chat observability"
```

### Task 5: Versioned persona and natural-language management

**Files:**
- Create: `src/avatar/brain/persona.py`
- Create: `src/avatar/brain/admin_agent.py`
- Modify: `src/avatar/brain/operations.py`
- Modify: `src/avatar/main.py`
- Modify: `src/avatar/web_api.py`
- Create: `frontend/src/features/persona/PersonaPage.tsx`
- Create: `frontend/src/features/persona/PersonaDiff.tsx`
- Create: `frontend/src/features/persona/PersonaPage.test.tsx`
- Create: `frontend/src/components/OperationConfirmDialog.tsx`
- Create: `frontend/src/components/OperationConfirmDialog.test.tsx`
- Test: `tests/test_persona_versions.py`
- Test: `tests/test_admin_agent.py`

**Interfaces:**
- Produces: `PersonaService.current()`, `history()`, `draft_update(changes)`, and executor for `persona.update`.
- Produces: `AdminAgent.propose(text: str, *, allow_cloud: bool = False) -> dict`; output must validate against a fixed operation schema.
- Produces: `GET /api/v1/persona`, `GET /api/v1/persona/history`, `POST /api/v1/persona/draft`, `POST /api/v1/admin-agent/draft`.
- Consumes: current persona in `Avatar._system_prompt`; environment persona is seed only after migration.

- [ ] **Step 1: Write failing persona lifecycle tests**

Cover initial migration, immutable history, stale parent rejection, activation, reverse draft, prompt consumption, rollback on audit failure and a restart preserving the active version.

- [ ] **Step 2: Run persona tests and verify RED**

Run: `python -m pytest tests/test_persona_versions.py -q`

- [ ] **Step 3: Implement persona service and operation executor**

Canonical fields: `name`, `core_identity`, `expression_principles`, `relationship_boundaries`, `immutable_rules`, `temperature_bias`, `initiative`. Validate lengths and numeric ranges server-side.

- [ ] **Step 4: Write failing admin-agent tests**

Use a transport double. Assert local model is selected by default, cloud requires `allow_cloud=True`, invalid JSON/unknown operations produce no draft, prompt injection cannot add operation types, and model unavailability leaves manual editing usable.

- [ ] **Step 5: Implement constrained admin-agent proposal**

The model produces proposal JSON only; `OperationService` recomputes the diff from trusted current state. Never execute the model response directly.

- [ ] **Step 6: Write failing frontend persona/confirmation tests**

Assert manual and natural-language changes show old/new values, warnings, expiry and confirm/cancel actions; no mutation fires before confirmation; expired/stale responses force a new preview.

- [ ] **Step 7: Implement persona UI and shared confirmation dialog**

- [ ] **Step 8: Verify Task 5**

Run: `python -m pytest tests/test_persona_versions.py tests/test_admin_agent.py tests/test_avatar_verifier.py -q`

Run: `npm --prefix frontend test -- --run`

- [ ] **Step 9: Commit**

```bash
git add src/avatar/brain/persona.py src/avatar/brain/admin_agent.py src/avatar/brain/operations.py src/avatar/main.py src/avatar/web_api.py frontend/src tests/test_persona_versions.py tests/test_admin_agent.py
git commit -m "feat: add versioned persona management"
```

### Task 6: Emotion override and memory control pages

**Files:**
- Create: `src/avatar/brain/emotion_overrides.py`
- Modify: `src/avatar/brain/emotion.py`
- Modify: `src/avatar/brain/operations.py`
- Modify: `src/avatar/web_api.py`
- Create: `frontend/src/features/emotion/EmotionPage.tsx`
- Create: `frontend/src/features/emotion/EmotionPage.test.tsx`
- Create: `frontend/src/features/memory/MemoryPage.tsx`
- Create: `frontend/src/features/memory/MemoryPage.test.tsx`
- Test: `tests/test_emotion_overrides.py`
- Test: `tests/test_memory_operation_api.py`

**Interfaces:**
- Produces: `EmotionOverrideService.active(now=None)`, `draft(values, duration_seconds, reason)`, executor for `emotion.override`.
- Produces: `GET /api/v1/emotion`, `POST /api/v1/emotion/draft`, versioned memory list/detail and `POST /api/v1/memory/batch-draft`.
- Consumes: existing `EmotionEngine` automatic state; override affects role expression only and expires without rewriting observations.

- [ ] **Step 1: Write failing override tests**

Cover bounded PAD values, minimum/maximum duration, active application, expiry, restart, replacement through a new confirmed draft, automatic-state preservation and audit rollback.

- [ ] **Step 2: Implement emotion override service and integration**

Keep observed user emotion and underlying role state intact. Return both automatic and effective state from the API.

- [ ] **Step 3: Write failing memory batch tests**

Cover mixed valid/invalid IDs, active/history separation, correction versus deletion, preview counts, stale version rejection and all-or-nothing execution.

- [ ] **Step 4: Implement memory draft adapter**

Reuse `MemoryStore.correct`, `forget` and trust/version rules; do not duplicate memory mutation SQL in `OperationService`.

- [ ] **Step 5: Write and implement frontend tests/pages**

Emotion tests cover PAD visualization, automatic/effective distinction, duration/reason and confirmation. Memory tests cover filters, source drawer, history, correction, dangerous deletion and batch preview.

- [ ] **Step 6: Verify Task 6**

Run: `python -m pytest tests/test_emotion.py tests/test_emotion_strategy.py tests/test_emotion_overrides.py tests/test_memory_operation_api.py tests/test_memory_lifecycle.py -q`

Run: `npm --prefix frontend test -- --run`

- [ ] **Step 7: Commit**

```bash
git add src/avatar/brain/emotion_overrides.py src/avatar/brain/emotion.py src/avatar/brain/operations.py src/avatar/web_api.py frontend/src/features/emotion frontend/src/features/memory tests
git commit -m "feat: add emotion and memory controls"
```

### Task 7: Previewed knowledge ingestion and retrieval

**Files:**
- Create: `src/avatar/brain/knowledge.py`
- Modify: `src/avatar/brain/operations.py`
- Modify: `src/avatar/web.py`
- Modify: `src/avatar/web_api.py`
- Create: `frontend/src/features/knowledge/KnowledgePage.tsx`
- Create: `frontend/src/features/knowledge/KnowledgePage.test.tsx`
- Test: `tests/test_knowledge.py`
- Test: `tests/test_knowledge_upload_api.py`

**Interfaces:**
- Produces: `KnowledgeService.preview_text`, `preview_file`, `execute_import`, `search`.
- Produces: `POST /api/v1/knowledge/preview-text`, `POST /api/v1/knowledge/preview-file`, `GET /api/v1/knowledge/sources`, `GET /api/v1/knowledge/search`; confirmation reuses `POST /api/v1/operations/{id}/confirm` from Task 3.
- Produces: executor for `knowledge.import`; preview stores bounded temporary content associated with draft expiry and deletes it after confirm/expiry.

- [ ] **Step 1: Write failing parser/chunk/dedup tests**

Use literal fixtures for UTF-8 text, Markdown headings, repeated paragraphs, near-duplicate chunks, empty content and deterministic chunk boundaries. Assert source metadata and rejected reasons.

- [ ] **Step 2: Write failing upload-security tests**

Cover `.txt`/`.md` allowlist, MIME mismatch, invalid UTF-8, NUL bytes, 5 MiB + 1 byte, traversal filename, unexpected multipart fields, partial reads and temporary-file cleanup.

- [ ] **Step 3: Implement knowledge service and upload boundary**

Required signatures:

```python
class KnowledgeService:
    def preview_text(self, title: str, text: str) -> dict: ...
    def preview_file(self, filename: str, stream, size: int) -> dict: ...
    def execute_import(self, preview: dict) -> dict: ...
    def search(self, query: str, *, limit: int = 8) -> list[dict]: ...
```

Use exact-hash and configured embedding similarity when available; deterministic lexical fallback must work without the embedding service.

- [ ] **Step 4: Write failing frontend knowledge tests**

Cover paste/file modes, progress, accepted/rejected chunk preview, duplicate labels, explicit confirm, expiry, parse error and source list.

- [ ] **Step 5: Implement knowledge UI**

- [ ] **Step 6: Verify Task 7**

Run: `python -m pytest tests/test_knowledge.py tests/test_knowledge_upload_api.py tests/test_embeddings.py -q`

Run: `npm --prefix frontend test -- --run`

- [ ] **Step 7: Commit**

```bash
git add src/avatar/brain/knowledge.py src/avatar/brain/operations.py src/avatar/web.py src/avatar/web_api.py frontend/src/features/knowledge tests/test_knowledge.py tests/test_knowledge_upload_api.py
git commit -m "feat: add previewed knowledge ingestion"
```

### Task 8: Tools health, audit UI and end-to-end confirmation flows

**Files:**
- Modify: `src/avatar/web_api.py`
- Create: `frontend/src/features/tools/ToolsPage.tsx`
- Create: `frontend/src/features/tools/ToolsPage.test.tsx`
- Create: `frontend/src/features/audit/AuditPage.tsx`
- Create: `frontend/src/features/audit/AuditPage.test.tsx`
- Create: `frontend/e2e/persona.spec.ts`
- Create: `frontend/e2e/emotion.spec.ts`
- Create: `frontend/e2e/memory.spec.ts`
- Create: `frontend/e2e/knowledge.spec.ts`
- Create: `frontend/playwright.config.ts`
- Test: `tests/test_tool_health_api.py`

**Interfaces:**
- Produces: `GET /api/v1/tools/health` with configured/available/last-error fields and no secrets.
- Audit page consumes Task 2 pagination and Task 3 reverse-draft endpoint.
- E2E harness starts an isolated temporary Python server and built frontend.

- [ ] **Step 1: Write failing tool-health and redaction tests**

Cover configured/unconfigured Ollama, reminders, knowledge and web tools; simulate exceptions; scan serialized responses for known test secrets.

- [ ] **Step 2: Implement health endpoint**

Health checks are bounded and read-only; a failing optional tool does not make the admin API unavailable.

- [ ] **Step 3: Write and implement frontend tools/audit tests**

Cover healthy/degraded/unconfigured states, audit filters, operation detail, failure display and reverse-draft preview. No “undo” button may execute immediately.

- [ ] **Step 4: Write Playwright flows first and observe failure**

Each spec must verify preview is visible before confirm, cancellation writes nothing, confirmation persists after reload, and an audit row references the resulting version/object.

- [ ] **Step 5: Complete integration until all four E2E flows pass**

Run: `npm --prefix frontend run e2e`

- [ ] **Step 6: Commit**

```bash
git add src/avatar/web_api.py frontend tests/test_tool_health_api.py
git commit -m "feat: complete admin audit and health views"
```

### Task 9: Compatibility removal gate, documentation and final verification

**Files:**
- Modify: `start_web.py`
- Modify: `src/avatar/web.py`
- Modify or remove after parity proof: `src/avatar/web_ui.py`
- Modify: `README.md`
- Modify: `docs/记忆工作台与提醒.md`
- Create: `docs/Mission-Control后台.md`
- Modify: `.gitignore`

**Interfaces:**
- Production `python start_web.py` serves `frontend/dist` and prints one authenticated local URL.
- Development commands are documented separately; no automatic npm install or cloud call occurs at runtime.

- [ ] **Step 1: Add a legacy/new API parity checklist test**

Assert chat, memory source/history/correction/deletion, reminders, summary and due-reminder operations are reachable through v1 before removing the old embedded page. Keep legacy API routes unless an explicit compatibility decision removes them later.

- [ ] **Step 2: Update startup behavior and documentation**

Document prerequisites, `npm ci`, dev server, production build, single-user security boundary, draft/confirm semantics, local-model default and backup guidance.

- [ ] **Step 3: Run frontend quality gates**

Run: `npm --prefix frontend run lint`

Run: `npm --prefix frontend test -- --run`

Run: `npm --prefix frontend run build`

Run: `npm --prefix frontend run e2e`

- [ ] **Step 4: Run complete backend verification**

Run: `python -m pytest tests/ -q`

Expected: all tests pass with zero failures.

- [ ] **Step 5: Run repository checks**

Run: `git diff --check`

Run a staged-diff secret scan for token/key patterns; verify `frontend/dist`, uploaded knowledge, SQLite data and temporary drafts are not staged unless intentionally documented.

- [ ] **Step 6: Manual acceptance pass**

Start `python start_web.py`; verify the authenticated URL opens Mission Control, every navigation route reloads, no console errors occur, narrow layout remains usable, and persona/emotion/memory/knowledge changes cannot bypass preview and confirmation.

- [ ] **Step 7: Commit**

```bash
git add start_web.py src/avatar/web.py src/avatar/web_ui.py README.md docs .gitignore
git commit -m "docs: complete Mission Control migration"
```
