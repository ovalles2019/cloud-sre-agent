# Cloud SRE Agent

**Autonomous Cloud Cost & Reliability Agent** — Bedrock-powered reasoning over CloudWatch metrics, AWS Cost Explorer, and Trusted Advisor, with a mandatory human-in-the-loop approval gate before any write remediation executes.

> Portfolio pitch: Production-shaped FinOps + SRE agent with Bedrock Converse reasoning, Lambda action groups for AWS APIs, DynamoDB incident/approval store, CDK infrastructure, and a live operations dashboard.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     FastAPI Control Plane (:8080)                     │
│   /v1/agent/analyze · /v1/approvals · /v1/incidents · /v1/dashboard  │
└────────────┬───────────────────────────────┬─────────────────────────┘
             │                               │
    ┌────────▼────────┐              ┌───────▼────────┐
    │ Bedrock Reasoner │              │ Approval Gate  │
    │ (Claude 3.5)     │              │ (HITL writes)  │
    └────────┬────────┘              └───────┬────────┘
             │                               │
    ┌────────▼───────────────────────────────▼────────────────────────┐
    │  CloudWatch · Cost Explorer · Trusted Advisor · Remediation      │
    └────────┬────────────────────────────────────────────────────────┘
             │
    ┌────────▼────────────────────────────────────────────────────────┐
    │  Lambda Action Groups (Bedrock Agent) · DynamoDB · API Gateway   │
    └──────────────────────────────────────────────────────────────────┘
```

### Agent workflow

1. **Collect** — Query CloudWatch for metric anomalies and active alarms; Cost Explorer for MTD spend drift; Trusted Advisor for optimization flags.
2. **Reason** — Bedrock Converse API (or rules engine fallback) correlates signals, drafts RCA, and ranks recommended actions.
3. **Gate** — Write-risk actions enter the approval queue; read-only investigation runs immediately.
4. **Remediate** — On approval, remediation executor runs the action (scale ASG, rollback Lambda, create budget, etc.) with audit trail.

---

## Quick start (local demo)

```bash
cd cloud-sre-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://localhost:8080** and click **Run agent analysis**. The demo mode uses realistic synthetic telemetry — no AWS credentials required.

### Live AWS mode

```bash
cp .env.example .env
# Set DEMO_MODE=false and configure AWS credentials
export AWS_PROFILE=your-profile
python app.py
```

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/dashboard` | GET | Health score, spend, incidents, sparklines |
| `/v1/agent/analyze` | POST | Run full agent analysis cycle |
| `/v1/incidents` | GET | List incident reports |
| `/v1/incidents/{id}` | GET | Get incident detail + agent trace |
| `/v1/approvals` | GET | List approval requests |
| `/v1/approvals/{id}/decide` | POST | Approve or reject write action |

---

## Deploy to AWS (CDK)

```bash
cd infra/cdk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap
cdk deploy
```

Creates:
- DynamoDB tables for incidents and approvals
- Lambda action group handler (CloudWatch, CE, TA, remediation)
- API Gateway for Bedrock Agent action groups
- IAM role for Bedrock Agent invocation

Wire the Lambda + OpenAPI schema (`lambdas/action_groups/openapi_schema.py`) into a Bedrock Agent in the console or extend the CDK stack.

---

## Project structure

```
cloud-sre-agent/
├── app.py                      # Uvicorn entrypoint
├── backend/
│   ├── main.py                 # FastAPI routes + static UI
│   ├── agent/orchestrator.py   # Telemetry + Bedrock reasoning
│   ├── services/approval.py    # Human-in-the-loop gate
│   ├── tools/                  # CloudWatch, CE, TA, remediation
│   └── store/repository.py     # Local / DynamoDB persistence
├── lambdas/action_groups/      # Bedrock Agent Lambda handlers
├── infra/cdk/                  # AWS CDK stack
└── web/                        # Operations dashboard UI
```

---

## Design decisions

- **Human-in-the-loop by default** — `require_approval_for_writes=true`; remediation Lambda validates `approval_token` in DynamoDB.
- **Demo-first** — Runnable without AWS for interviews and UX demos; flip `DEMO_MODE=false` for live telemetry.
- **Bedrock Agent-ready** — OpenAPI action groups mirror the local tool layer for seamless migration to managed Bedrock Agents.

---

## License

MIT
