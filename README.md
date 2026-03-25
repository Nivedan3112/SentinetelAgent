# SentinetelAgent# 🛡️ Sentinel — AI SRE Agent

> An autonomous on-call assistant that triages alerts, runs diagnostic runbooks, and posts structured incident reports — powered by Claude's tool_use API in an agentic loop.

[![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude%20claude-sonnet-4-20250514-6c8eff?style=flat-square)](https://anthropic.com)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue?style=flat-square)](https://python.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ed?style=flat-square)](docker-compose.yml)

## What it does

When an alert fires, Sentinel runs a full investigation:

```
Alert (Prometheus / PagerDuty / Datadog / CloudWatch)
    │
    ▼
FastAPI webhook ingest  →  Redis queue
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Sentinel Agent — Claude claude-sonnet-4-20250514           │
│                                                     │
│  triage_alert → check_metrics → query_logs          │
│      → run_runbook → draft_postmortem → notify_slack│
│                                                     │
│  tool_use agentic loop · ≤15 iterations             │
└─────────────────────────────────────────────────────┘
    │
    ▼
Slack #incidents  ·  Confluence PM  ·  Postgres  ·  Grafana
```

**Human-in-the-loop by design:** every production action is flagged `requires_approval: true`.

## Quick start

### Demo mode (no API key needed)
```bash
git clone https://github.com/yourorg/sentinel
cd sentinel
pip install -r requirements.txt
uvicorn ingest.main:app --reload
```

### With Claude API
```bash
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn ingest.main:app --reload
```

### Docker Compose
```bash
cp .env.example .env
docker compose up
```

## Project structure

```
sentinel/
├── agent/
│   ├── orchestrator.py        # Claude agentic loop
│   ├── demo_orchestrator.py   # Demo mode (no key needed)
│   ├── prompts.py             # SRE system prompt
│   └── tools/
│       ├── triage.py
│       ├── check_metrics.py
│       ├── query_logs.py
│       ├── run_runbook.py     # 5 runbooks
│       ├── draft_postmortem.py
│       └── notify.py
├── ingest/main.py             # FastAPI webhooks + REST API
├── static/index.html          # POC dashboard
├── tests/test_tools.py        # 12 unit tests
├── docker-compose.yml
└── requirements.txt
```

## Available runbooks

| Runbook | Diagnoses |
|---------|-----------|
| `high-memory` | OOMKill, heap exhaustion, memory leaks |
| `high-latency` | Connection pool saturation, circuit breakers |
| `disk-full` | Log bloat, heap dumps, volume sizing |
| `pod-crashloop` | CrashLoopBackOff, bad deployments |
| `db-connection-exhaustion` | PG max_connections, long queries |

## Tests

```bash
pytest tests/ -v   # no API key required
```

## License

MIT — Built with [Anthropic Claude](https://anthropic.com) · claude-sonnet-4-20250514 · tool_use API
