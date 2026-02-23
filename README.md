# Mycroft

AI agent system for autonomous software delivery. A WebSocket-based pipeline that guides product ideas through specs, architecture, planning, and implementation — producing working code with tests.

## Pipeline

| Step | Name | Description |
|------|------|-------------|
| 0 | Idea Scoping | Refine a product idea into a clear problem statement |
| 1 | Use Cases | Generate or manually define user stories and acceptance criteria |
| 2 | Architecture | Design system architecture (C4 model) with manual or AI-assisted mode |
| 3.1 | Project Setup | Create GitHub repo from template + Linear project |
| 3.2 | C4 Design | Decompose into modules, classes, functions; create Linear stories |
| 4 | Work Planning | Dependency ordering, priorities, parallelization in Linear |
| 5 | Execution | Team Leads (Claude Agent SDK) dispatch sub-agents: CodeWriter, UnitTester, QATester |
| 6 | E2E Testing | Integration tests, spec validation, build verification |

## Project Structure

```
src/mycroft/
  server/          # FastAPI backend, WebSocket, pipeline agents, state management
    agents/        # BaseAgent + per-step agent implementations
    pipeline/      # Pipeline orchestration and step registry
    worker/        # Team leads, sub-agents, blocker mechanism
    linear/        # GraphQL client for Linear API
    git/           # Git operations (worktrees, branches, PRs)
    ws/            # WebSocket handler and stream relay
    state/         # ProjectState persistence (JSON)
  client/          # Typer CLI with Rich UI and WebSocket client
  shared/          # Pydantic protocol models shared between server and client
templates/         # Jinja2 templates for agents and worker prompts
config/            # TOML configuration (server, client, security paths)
tests/             # Unit tests (pytest + pytest-asyncio)
```

## Setup

### Prerequisites

- Python 3.11+
- API keys: `ANTHROPIC_API_KEY`, `LINEAR_API_KEY`, `GITHUB_TOKEN`

### Local

```bash
# Install all extras
pip install -e ".[server,client,dev]"

# Copy and fill in environment variables
cp .env.example .env

# Start the server
mycroft-server

# In another terminal, connect the CLI
mycroft
```

### Docker

```bash
# Build
docker compose build

# Run server
docker compose up server

# Run tests
docker compose run --rm test

# Run linter
docker compose run --rm lint
```

## Testing

```bash
# All tests
pytest

# Verbose
pytest -v

# Single test module
pytest tests/test_server/test_agents.py
```

## Configuration

Configuration lives in `config/` as TOML files:

- **`server.toml`** — Server settings (host, port, data directory, API endpoints)
- **`client.toml`** — CLI settings (server URL, display preferences)
- **`security_paths.toml`** — Glob patterns for files requiring human review on PRs

Environment variables (via `.env`) override TOML values. Key variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API access |
| `LINEAR_API_KEY` | Linear project management |
| `GITHUB_TOKEN` | GitHub repo and PR operations |
