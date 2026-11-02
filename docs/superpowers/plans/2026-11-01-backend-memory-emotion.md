# Backend Memory and Emotion Implementation Plan

> For agentic workers: use subagent-driven-development; execute tasks sequentially with scoped review. User approved the preceding five-part design. No additional approval or commits are needed.

**Goal:** Reliable evolving memory, independent emotion/strategy, traceable controls, semantic recall and reproducible dialogue evaluation.
**Architecture:** Additive SQLite metadata and sources, fact normalization at the input boundary, separate user/role state, optional injected embedding provider. Integrate through Avatar with compatible defaults.
**Tech Stack:** Python >=3.10, SQLite, NumPy, existing OpenAI-compatible interface, optional local Ollama embedding HTTP.
**Spec:** ../specs/2026-11-01-backend-memory-emotion.md

## Global Constraints
- No .env or production data edits; no new mandatory heavy dependencies; no commits/pushes.
- Existing callers remain compatible except current recall intentionally excludes superseded facts.
- Raw model candidates never bypass source/subject/modality checks.
- Preserve atomic batches and keyword-only fallback if embedding is unavailable.

## Review Focus
- Legacy database upgrades are idempotent and preserve facts without resurrecting obsolete profile values.
- Deleted facts do not reappear in vector results, source messages or short-term prompts.
- Quoted/conditional/other-person facts remain rejected during temporal normalization.
- Embedding errors/model changes do not lose memory or mix vector dimensions.
- Negative user feelings do not create an angry role; explicit help/no-advice overrides old intent.

## Task 1: Memory lifecycle and sources
Files: brain/memory.py; tests/test_memory.py; new tests/test_memory_lifecycle.py.
Interfaces: MemoryStore(..., embedder=None); remember(..., source_message_id=None, evidence=None); remember_user(key,value,*,source_message_id=None,evidence=None)->int; add_message(role,content,session_id)->int; inspect(id)->dict|None; list_memories(include_history=False,limit=100)->list; correct(id,content,*,evidence='manual correction')->int; forget(id); history via include_history.
- [x] Write/run failing migration, conflicting preference, duplicate, provenance/reopen, correct, forget/legacy resurrection and rollback tests.
- [x] Implement additive status/validity/profile/preference metadata; sources/messages tables and transactional controls.
- [x] Current-only recall/profile; optional include_history parameter for deliberate inspection. Preserve old generic CRUD.
- [x] Run targeted/full tests and scoped review; document intentional test updates.

## Task 2: Emotion and strategy
Files: brain/emotion.py; tests/test_emotion.py; new tests/test_emotion_strategy.py.
Interfaces: EmotionEngine(decay=0.15,clock=None); user_state observation; state role; observe(valence,arousal,text='')->role state; decide(text)->Decision with strategy; compatibility update/update_from route through observe.
- [x] Failing clock decay, anger isolation, no-advice/help/celebration strategy tests.
- [x] Implement separate states, real elapsed-time decay and strategy behavior; keep Decision legacy fields.
- [x] Targeted tests plus scoped review.

## Task 3: Temporal evidence and Avatar integration
Files: brain/facts.py; main.py; tests/test_facts.py; tests/test_main.py; new integration tests.
- [x] Failing explicit and same/cross-turn ellipsis updates, quote/hypothesis guards and source linkage tests.
- [x] Extend rule_facts(text,context=None), supported_fact(text,candidate,context=None) with unambiguous object resolution only; normalize current polarity, suppress obsolete predecessor.
- [x] Avatar records messages/session ids; stores validated evidence, calls emotion.observe; prompts show current state and strategy, memory is quoted data. Expose list/inspect/correct/forget wrappers and CLI slash commands; edits clear short-term context.
- [x] Full regressions and scoped review.

## Task 4: Optional semantic retrieval
Files: new brain/embeddings.py; brain/memory.py; config.py; main.py; .env.example; new tests/test_semantic_memory.py.
Interfaces: EmbeddingProvider.model_id:str, embed(text)->list[float]; OllamaEmbeddingProvider(base_url,model,timeout); MemoryStore.reindex()->int; hybrid recall uses active/type-filtered vectors.
- [x] Failing paraphrase retrieval, lexical fallback, malformed vectors, changed model/dimension, deleted/superseded exclusion and rollback tests.
- [x] Implement lazy vectors and cosine scoring/model metadata. Configure EMBEDDING_MODEL empty by default and EMBEDDING_BASE_URL localhost; retrieval failure never breaks chat.
- [x] Real local embedding smoke test in isolated DB, full suite and scoped review.

## Task 5: Dialogue evaluation and docs
Files: scripts/evaluate_backend.py; tests/test_dialogue_scenarios.py; docs/backend.md; README.md; docs/项目进度.md.
- [x] Deterministic multi-session scenarios covering all five features with checks for evidence, active facts, strategy and absent forgotten content.
- [x] Real local model tests, structured raw reports and latency/limitations; document memory controls and embedding opt-in setup.
- [x] Whole-change code/security review, resolve material issues, run full suite and diff checks.
- [x] Back up/hash-check originals, sync only changed source/tests/docs, verify actual repository. Deliver report without commits.
