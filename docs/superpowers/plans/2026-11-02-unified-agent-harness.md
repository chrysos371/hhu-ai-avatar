# Unified Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify reminder, local document, web and weather tools behind one bounded Python agent loop.

**Architecture:** A typed registry validates calls before an MCP session receives them. One stdio assistant server exposes all capabilities, while `WebAgent` remains as a compatibility alias for the new loop.

**Tech Stack:** Python 3.10+, MCP 1.x, SQLite, pytest, Open-Meteo HTTPS API

**Spec:** `docs/superpowers/specs/2026-11-02-unified-agent-harness-design.md`

## Global Constraints

- Preserve the existing memory and emotion behavior.
- Maximum three tool calls per turn.
- Local documents require explicit allowlisted roots.
- No secrets or complete inherited environment are forwarded to MCP.

## Review Focus

- Unknown tools and extra arguments must be rejected before MCP execution.
- Reminder writes must retain the existing explicit-time parser.
- Document symlinks and hidden files must not escape roots.
- Weather provider failures must remain explicit.
- Existing `/search`, `/read`, and web UI behavior must remain compatible.

---

### Task 1: Registry and weather tool

**Files:** Create `src/avatar/tools/tool_registry.py`, `src/avatar/tools/weather.py`; test `tests/test_tool_registry.py`, `tests/test_weather.py`.

- [ ] Write failing validation and weather-normalization tests.
- [ ] Run the tests and confirm expected failures.
- [ ] Implement minimal registry and weather query.
- [ ] Run targeted tests.

### Task 2: Unified MCP server and session

**Files:** Modify `src/avatar/tools/assistant_server.py`, `src/avatar/tools/web_client.py`; test `tests/test_assistant_mcp.py`.

- [ ] Write a failing real stdio lifecycle test with temporary documents/database.
- [ ] Pass only required environment and expose seven tools.
- [ ] Run the integration test.

### Task 3: Generic agent loop and Avatar integration

**Files:** Create `src/avatar/tools/agent_loop.py`; modify `src/avatar/tools/web_agent.py`, `src/avatar/main.py`, `src/avatar/web.py`, `src/avatar/web_ui.py`; tests in `tests/test_agent_loop.py` and existing suites.

- [ ] Write failing routing, bounds and compatibility tests.
- [ ] Implement the loop and compatibility alias.
- [ ] Connect the web toggle to all assistant tools.
- [ ] Run targeted and full regression tests.

### Task 4: Documentation and delivery

**Files:** Modify `.env.example`, `README.md`, `docs/MCP联网工具.md`.

- [ ] Document roots, reminder write boundary, weather and launch behavior.
- [ ] Run `git diff --check` and full pytest.
