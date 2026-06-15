# Render + AWS live mode setup

## 1. Deploy on Render

**One-click:** https://render.com/deploy?repo=https://github.com/ovalles2019/cloud-sre-agent

After deploy, your URL will be `https://cloud-sre-agent.onrender.com` (or similar).

Verify: `curl https://YOUR-SERVICE.onrender.com/healthz`

Expected demo response:
```json
{
  "status": "ok",
  "runtime": "demo",
  "demo_mode": true,
  "aws_configured": false
}
```

---

## 2. Create an AWS IAM user for the agent

Use a dedicated IAM user — never your root account keys.

```bash
aws iam create-user --user-name cloud-sre-agent-render
aws iam put-user-policy \
  --user-name cloud-sre-agent-render \
  --policy-name CloudSreAgentPolicy \
  --policy-document file://infra/iam/cloud-sre-agent-policy.json
aws iam create-access-key --user-name cloud-sre-agent-render
```

Save the `AccessKeyId` and `SecretAccessKey` from the output.

### Required AWS setup

| Service | Requirement |
|---------|-------------|
| **Bedrock** | Enable Claude 3.5 Sonnet in Bedrock console (us-east-1) |
| **Cost Explorer** | Enable in Billing → Cost Explorer (takes ~24h first time) |
| **Trusted Advisor** | Requires Business or Enterprise Support plan |
| **DynamoDB** | Optional — deploy CDK stack for persistent incidents |

---

## 3. Wire credentials in Render

In **Render Dashboard → cloud-sre-agent → Environment**, add:

| Key | Value |
|-----|-------|
| `AWS_ACCESS_KEY_ID` | Your IAM access key |
| `AWS_SECRET_ACCESS_KEY` | Your IAM secret key |
| `DEMO_MODE` | `false` |
| `USE_LOCAL_STORE` | `true` (or `false` if using DynamoDB tables) |

Click **Save Changes** — Render redeploys automatically.

After redeploy, verify live mode:
```bash
curl https://YOUR-SERVICE.onrender.com/healthz
```

Expected:
```json
{
  "runtime": "live-aws",
  "demo_mode": false,
  "aws_configured": true,
  "public_url": "https://cloud-sre-agent.onrender.com"
}
```

---

## 4. Optional: DynamoDB persistence

For production incident/approval storage across restarts:

```bash
cd infra/cdk && cdk deploy
```

Then in Render environment:
```
USE_LOCAL_STORE=false
DYNAMODB_INCIDENTS_TABLE=cloud-sre-incidents
DYNAMODB_APPROVALS_TABLE=cloud-sre-approvals
```

---

## 5. Custom domain (later)

If you add a domain later, in Render **Settings → Custom Domains**:

1. Add your domain (e.g. `sre.yourdomain.com`)
2. Create a CNAME pointing to `cloud-sre-agent.onrender.com`
3. Wait for TLS certificate issuance (~2–5 min)

Or uncomment `domains` in `render.yaml` and redeploy the Blueprint.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Still shows `demo` after adding creds | Set `DEMO_MODE=false` explicitly |
| Bedrock access denied | Enable model access in Bedrock console for us-east-1 |
| Cost Explorer empty | Enable Cost Explorer in AWS Billing; wait 24h |
| Free tier spin-down | First request after idle may take ~30s (cold start) |
| Approvals lost on restart | Set `USE_LOCAL_STORE=false` + deploy DynamoDB tables |
