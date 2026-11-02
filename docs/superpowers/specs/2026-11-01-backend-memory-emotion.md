# Backend memory and emotion upgrade

User approved all five follow-ups: temporal preference updates, separate user/role emotion, durable provenance and memory controls, broader dialogue evaluation, semantic recall.

Keep Python >=3.10, SQLite, explainable fact gates and decision tree, and existing public calls compatible. No new mandatory heavy dependencies. Do not read or modify .env, production data, audio or rendering. Work in the existing isolated staging checkout, back up and hash-check before syncing source to the original repository. No commits/pushes.

## Memory

Add idempotent SQLite migrations. Every current fact has active/superseded status, validity times, optional predecessor, profile key, preference canonical object/polarity. New current preference for the same object supersedes its predecessor; distinct objects coexist; repeats add provenance without duplication. Single-value attributes supersede old records. Historical rows never enter ordinary recall, profiles or vector results. Existing data is migrated conservatively and legacy superseded values cannot resurrect after deletion.

Persist user/assistant messages (session id, role, time), and fact evidence linked to source messages. Expose listing, history, inspect, correction and hard deletion. Deletion removes linked sources/tags/embedding; for privacy remove/redact source message text when needed, and clear short-term context after a user memory edit. User correction creates a new validated manual version. Inspect sources must remain useful after reopening a database. A failed round cannot leave half a fact batch.

Temporal language: explicit current changes and same-sentence old/current ellipsis resolve the referenced object when unambiguous. Cross-turn ellipsis can use exactly one recent explicit preference; ambiguous objects cause abstention, not guesses. Historical facts remain history. Existing hypothesis, question, quote and other-person guards remain binding.

## Emotion

Maintain latest user observation separately from role state. Role state relaxes toward a neutral baseline with elapsed time using an injectable clock, and does not mirror user's anger. Choose explicit strategy: listen, clarify, empathize, advise, celebrate, answer. Requests for practical help override lingering support style; explicit no-advice requests choose listen. Existing Decision fields and state access remain compatible; add strategy and user observation metadata to responses. Strategy drives prompts and fallback replies, not only temperature.

## Semantic recall

Inject an embedding provider into MemoryStore. Implement local Ollama /api/embed with stdlib HTTP and NumPy cosine similarity. Store vector/model identity; never mix model spaces or dimensions. Hybrid recall merges lexical/semantic candidates after active/type filters. Provider errors fall back to lexical recall without corrupting facts. Lazy indexing/reindex method handles existing facts and changed model identity. Configure optional embedding via environment, disabled by default; document setup and exercise a real local embedding model in an isolated test.

## Verification

Preserve existing regression tests except intentional updated semantics. Add legacy migration, reopen, nested rollback, preference changes, source inspection, correction/deletion, semantic paraphrase, provider failure/dimension/model mismatch, no obsolete retrieval, emotional strategy transitions, and multi-session dialogue tests. Include an executable seeded local model eval producing JSON/Markdown with honest separate accuracy/abstention/latency. No tiny-score claims about general model capability.
