# AI Sales Agent

An AI-powered sales agent that responds to inbound leads automatically.

Works with **any CRM or lead source** that supports outbound webhooks — Salesforce, Pipedrive, Zoho, or a plain HTML form. The demo is built using **HubSpot Workflows**, but swapping the trigger is just a matter of pointing a different webhook at the same endpoint.

When a lead comes in, this agent:
1. Receives the contact via webhook
2. Retrieves relevant context from your indexed website (HydraDB)
3. Drafts a personalised reply using Kimi K2 (GMI Cloud)
4. Sends a branded HTML email to the lead via Gmail

Fully configurable — point it at any agency or website by changing a few `.env` variables.

---

## Architecture

```
HubSpot Workflow
      │
      ▼
POST /hubspot-webhook  (AWS Lambda / local FastAPI)
      │
      ├── parse lead (name, email, message)        utils.py
      ├── extract keyword queries via Kimi          helpers.py
      ├── BM25 recall from HydraDB                 helpers.py
      ├── draft reply email via Kimi               routes.py
      └── send branded HTML email via Gmail SMTP   utils.py
```

---

## Project Structure

```
.
├── agent.py              # Local dev entry point (uvicorn on port 3000)
├── routes.py             # FastAPI app, endpoints, email prompt
├── helpers.py            # HydraDB recall logic
├── utils.py              # GMI LLM calls, Gmail SMTP, HubSpot parsing
├── serverless.yml        # AWS Lambda deployment (Serverless Framework v4)
├── Dockerfile            # Alternative container image deployment
├── requirements.txt      # Python dependencies
└── seed/
    └── prepare_kb.py     # Web crawler + HydraDB indexer
```

---

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file:

```env
# HydraDB
HYDRADB_API_KEY=sk_live_...

# GMI Cloud (Kimi K2)
GMI_API_KEY=eyJhbGci...

# Gmail SMTP (use an App Password, not your account password)
GMAIL_USER=you@yourdomain.com
GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_SENDER_NAME=Your Name

# Agency branding (controls prompts, email header/footer, CTA button)
AGENCY_NAME=Your Agency
AGENCY_URL=https://youragency.com
AGENCY_TAGLINE=HubSpot Platinum Partner
AGENCY_CALENDAR_URL=https://meetings.hubspot.com/yourlink

# Seeder (optional — defaults shown)
SEED_TENANT_ID=my-agency
SEED_START_URL=https://youragency.com
SEED_DELAY=0.8
SEED_MAX_PAGES=0
```

> Generate a Gmail App Password at: Google Account → Security → 2-Step Verification → App passwords

### 3. Seed the knowledge base

Crawl and index your website into HydraDB before running the agent:

```bash
python seed/prepare_kb.py
```

**Seeder options** (all set via `.env`):

| Variable | Default | Description |
|---|---|---|
| `SEED_TENANT_ID` | `hubbase` | HydraDB tenant to index into |
| `SEED_START_URL` | `https://www.hubbase.io` | Root URL to crawl |
| `SEED_DELAY` | `0.8` | Seconds between page fetches |
| `SEED_MAX_PAGES` | `0` | Max pages to index (0 = unlimited) |

---

## Running Locally

```bash
python agent.py
```

Server starts at `http://localhost:3000`.

Expose it to HubSpot using [ngrok](https://ngrok.com):

```bash
ngrok http 3000
```

---

## Endpoints

### `POST /hubspot-webhook`
Receives a HubSpot workflow webhook, drafts and sends a reply email.

**Expected payload** (HubSpot workflow format):
```json
{
  "properties": {
    "email":     { "value": "lead@example.com" },
    "firstname": { "value": "Jane" },
    "lastname":  { "value": "Doe" },
    "message":   { "value": "What does a HubSpot CRM migration cost?" }
  }
}
```

**Response:**
```json
{
  "lead_email": "lead@example.com",
  "email_sent": true,
  "draft": "Hi Jane, ..."
}
```

### `POST /webhook`
Generic recall + answer endpoint (no email sent). Useful for testing recall.

```json
{ "message": "what services do you offer?", "top_k": 5 }
```

### `GET /health`
Returns service status.

---

## Deploying to AWS Lambda

### Prerequisites
- [Serverless Framework v4](https://www.serverless.com/) — `npm install -g serverless`
- AWS profile configured (set `profile:` in `serverless.yml`)
- [Docker](https://www.docker.com/) running (required to build Linux-compatible wheels)

### Deploy

```bash
serverless deploy --stage dev
```

### Teardown

```bash
serverless remove --stage dev
```

### Updating environment variables without redeploying

```bash
aws lambda update-function-configuration \
  --function-name <service-name>-dev-api \
  --environment "Variables={GMAIL_PASSWORD=new_password}" \
  --profile <your-aws-profile> --region us-east-1
```

---

## HubSpot Workflow Setup

1. Go to **HubSpot → Automations → Workflows**
2. Create a contact-based workflow triggered on form submission
3. Add a **Webhook** action:
   - Method: `POST`
   - URL: `https://<your-lambda-url>/hubspot-webhook`
   - Include contact properties: `email`, `firstname`, `lastname`, `message`
4. Enroll contacts and test

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent framework | FastAPI + Mangum |
| LLM | Kimi K2 Instruct via GMI Cloud |
| Memory / RAG | HydraDB (BM25 recall, `alpha=0`) |
| Email | Gmail SMTP with branded HTML template |
| Deployment | AWS Lambda (Serverless Framework v4) |
| Crawler | Python `requests` + `BeautifulSoup` |
