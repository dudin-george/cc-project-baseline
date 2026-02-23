# Plan: AI Agent System for Autonomous Software Delivery

## Context

Build a template-driven pipeline where product specs written in Linear are autonomously decomposed into tickets and implemented by AI agents — without opening an IDE. The system runs as a daemon on a VPS: it listens for locked specs via Linear webhooks, decomposes them into small tickets using Claude Opus, then spawns Claude Code headless (Sonnet) workers in isolated git worktrees to implement each ticket, run tests, and push PRs. Non-security PRs auto-merge through GitHub Actions CI; security-critical PRs (identified by file path rules + Linear labels) require human approval.

---

## Architecture Overview

```
Linear (specs + tickets)
    │
    ▼ webhook (spec locked)
┌─────────────────────────────┐
│  FastAPI Webhook Listener   │  ← receives Linear events
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│  Spec Decomposer (Opus)     │  ← breaks spec into templated tickets
│  anthropic SDK + templates  │
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│  Linear Client              │  ← creates sub-issues in Linear
│  (GraphQL over httpx)       │
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│  Worker Manager              │  ← queue + concurrency pool
│  (asyncio + semaphore)       │
└────────────┬────────────────┘
             ▼ (per ticket)
┌─────────────────────────────┐
│  Worker Executor             │  ← isolated git worktree
│  claude -p (Sonnet headless) │  ← read/write/test/fix/commit
│  gh pr create                │  ← push PR with labels
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│  GitHub Actions CI           │  ← tests + lint + auto-merge
│  (non-security = auto-merge) │
│  (security = require review) │
└──────────────────────────────┘
```

---

## Directory Structure

```
src/
  orchestrator/
    __init__.py
    main.py                  # Daemon entry point (uvicorn + startup tasks)
    settings.py              # Pydantic Settings (env vars, project config)
    linear/
      __init__.py
      client.py              # Async GraphQL client (httpx)
      webhook.py             # FastAPI router: webhook receiver + HMAC verification
      models.py              # Pydantic models for Linear entities
    decomposer/
      __init__.py
      engine.py              # Opus-based spec → ticket decomposition
      templates.py           # Load and render ticket templates
    worker/
      __init__.py
      manager.py             # Async worker pool, queue, concurrency control
      executor.py            # Claude Code headless execution per ticket
    git/
      __init__.py
      worktree.py            # Git worktree create/cleanup
      pr.py                  # PR creation, labeling (security vs non-security)

templates/                   # Ticket templates (Jinja2 markdown)
  feature.md.j2
  bugfix.md.j2
  refactor.md.j2
  test.md.j2
  infra.md.j2

config/
  default.toml               # Default settings
  security_paths.toml         # File path rules for security-critical PRs

tests/
  test_decomposer.py
  test_worker.py
  test_linear_client.py
  test_webhook.py

pyproject.toml
Dockerfile
docker-compose.yml            # For VPS deployment
```

---

## Key Components

### 1. Settings (`src/orchestrator/settings.py`)
- Pydantic Settings loading from env vars + TOML config
- Fields: `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`
- Per-project config: repo URL, base branch, max workers, max cost per ticket, max turns
- Security path rules (glob patterns for files requiring human review)

### 2. Linear Webhook Listener (`src/orchestrator/linear/webhook.py`)
- FastAPI router mounted at `/webhooks/linear`
- HMAC-SHA256 signature verification on every request
- Filters for issue state change events where new state = "Locked" (configurable state name)
- Extracts spec issue ID, passes to decomposer

### 3. Linear Client (`src/orchestrator/linear/client.py`)
- Thin async wrapper over Linear's GraphQL API using `httpx`
- Methods: `get_issue(id)`, `create_issue(input)`, `update_issue(id, input)`, `get_workflow_states(team_id)`
- Handles pagination, error responses, rate limit headers
- No third-party Linear SDK dependency (GraphQL is simple enough, avoids version churn)

### 4. Spec Decomposer (`src/orchestrator/decomposer/engine.py`)
- Calls Claude Opus via `anthropic` SDK with structured output (tool_use)
- Input: spec text from Linear issue + project context (CLAUDE.md, file tree summary)
- Output: list of tickets, each with: title, description, type (feature/bugfix/refactor/test/infra), dependencies, security_critical flag
- Uses Jinja2 templates from `templates/` to format ticket descriptions consistently
- Templates include: acceptance criteria, file hints, test requirements, coding conventions

### 5. Worker Manager (`src/orchestrator/worker/manager.py`)
- Async queue (asyncio.Queue) fed by decomposer
- Semaphore-based concurrency limit (configurable, default 3 parallel workers)
- Respects ticket dependencies — tickets with `blocked_by` wait until blockers complete
- Tracks worker status, reports back to Linear (in-progress, done, failed)

### 6. Worker Executor (`src/orchestrator/worker/executor.py`)
- For each ticket:
  1. Create isolated git worktree (`git worktree add`)
  2. Build prompt from ticket description + template + project CLAUDE.md
  3. Run `claude -p "<prompt>" --output-format json --allowedTools "Bash(git *),Bash(npm *),Bash(pytest *),Read,Edit,Write,Grep,Glob" --max-turns 25 --max-budget-usd 5.00`
  4. Parse JSON output for success/failure
  5. On failure: retry once with error context (`claude -r <session_id> -p "fix the issue"`)
  6. On success: push branch, create PR via `gh pr create`
  7. Label PR: `auto-merge` or `security-review-required`
  8. Update Linear ticket status
  9. Cleanup worktree

### 7. PR Pipeline (`src/orchestrator/git/pr.py`)
- Determine if PR is security-critical:
  - Check if Linear ticket has `security_critical` flag (from decomposition)
  - Check if any changed files match patterns in `security_paths.toml`
  - If either matches → label `security-review-required`, don't auto-merge
- Non-security PRs get `auto-merge` label
- GitHub Actions workflow (separate file) enables auto-merge for PRs with `auto-merge` label that pass CI

### 8. GitHub Actions CI (`.github/workflows/`)
- `ci.yml`: lint + test on every PR
- `auto-merge.yml`: auto-merge PRs with `auto-merge` label when CI passes (uses `gh pr merge --auto --squash`)

---

## Ticket Templates

Templates are Jinja2 markdown files. Example `feature.md.j2`:

```markdown
## Task: {{ title }}

### Description
{{ description }}

### Acceptance Criteria
{% for criterion in acceptance_criteria %}
- [ ] {{ criterion }}
{% endfor %}

### Implementation Hints
- Target files: {{ target_files | join(', ') }}
- Related modules: {{ related_modules | join(', ') }}

### Testing Requirements
- Write unit tests for all new functions
- Ensure existing tests still pass
- Run: `{{ test_command }}`

### Constraints
- Follow patterns in CLAUDE.md
- Do not modify files outside the scope of this ticket
- {{ project_conventions }}
```

The decomposer fills these templates with data from Opus's structured output.

---

## Build Order (MVP → Full)

### Phase 1: Core Pipeline (MVP)
1. **`settings.py`** — config loading, validation
2. **`linear/client.py`** — GraphQL client (get issue, create issue, update status)
3. **`linear/webhook.py`** — FastAPI webhook handler with signature verification
4. **`decomposer/engine.py`** — Opus decomposition with one template (feature.md.j2)
5. **`worker/executor.py`** — Claude Code headless execution in worktrees
6. **`git/worktree.py`** — worktree create/cleanup
7. **`git/pr.py`** — PR creation with basic labeling
8. **`main.py`** — wire it all together, uvicorn startup

### Phase 2: Robustness
9. **`worker/manager.py`** — async queue, concurrency control, dependency ordering
10. Error handling: retries, dead-letter reporting to Linear
11. Additional templates (bugfix, refactor, test, infra)
12. Security path rules + dual detection (labels + file paths)

### Phase 3: Production
13. Dockerfile + docker-compose for VPS deployment
14. GitHub Actions workflows (ci.yml, auto-merge.yml)
15. Logging, monitoring, cost tracking
16. Per-project config overrides

---

## Verification Plan

1. **Unit tests**: Mock Linear API responses, mock Claude Code subprocess, test decomposer output structure
2. **Integration test**: Use a test Linear workspace + test GitHub repo:
   - Create a spec issue, lock it
   - Verify webhook fires and decomposer creates tickets
   - Verify worker creates worktree, runs Claude Code, pushes PR
   - Verify PR has correct labels
3. **End-to-end**: Lock a real spec in Linear, watch the full pipeline execute, verify PR appears in GitHub
4. **Cost safety**: Verify `--max-budget-usd` and `--max-turns` limits are respected

---

## Key Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "httpx>=0.28",
    "anthropic>=0.52",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "jinja2>=3.1",
    "tomli>=2.0",  # for config parsing on Python <3.11
]
```

External tools required on VPS: `git`, `gh` (GitHub CLI), `claude` (Claude Code CLI), `node`/`npm` or `python`/`pytest` (depending on target projects).
