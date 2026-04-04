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
├── agent.py                     # Local dev entry point (uvicorn on port 3000)
├── routes.py                    # FastAPI app, endpoints, email prompt
├── helpers.py                   # HydraDB recall logic
├── utils.py                     # GMI LLM calls, Gmail SMTP, HubSpot parsing
├── hubspot_app.py               # HubSpot action definition, signature verification, registration
├── register_hubspot_action.py   # One-time script to register/update the workflow action
├── serverless.yml               # AWS Lambda deployment (Serverless Framework v4)
├── requirements.txt             # Python dependencies
└── seed/
    └── prepare_kb.py            # Web crawler + HydraDB indexer
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

## HubSpot Workflow Extension Setup

The agent integrates with HubSpot as a **Custom Workflow Action** — it appears natively in the HubSpot workflow builder as a reusable action step.

### App-level: Register the workflow action (once, by the developer)

The action definition lives at the HubSpot app level and is shared across all portals that install the app. Register or update it using:

```bash
python register_hubspot_action.py
```

Required `.env` vars:

```env
HUBSPOT_APP_ID=               # From your HubSpot developer app settings
HUBSPOT_DEVELOPER_API_KEY=    # From developers.hubspot.com → Apps → API key
LAMBDA_URL=                   # Base URL of the deployed Lambda, e.g. https://xyz.execute-api.us-east-1.amazonaws.com
HUBSPOT_DEFINITION_ID=        # Optional — if set, PATCHes the existing action instead of creating a new one
```

The script will print the new action's `id` — save it as `HUBSPOT_DEFINITION_ID` for future updates.

To unpublish or republish an action without re-registering, use the HubSpot Automation API directly or run a quick Python snippet against `https://api.hubapi.com/automation/v4/actions/{app_id}/{definition_id}`.

### Portal-level: Install the app (once per HubSpot portal)

Portals install the app via OAuth. Send the portal admin to:

```
https://app.hubspot.com/oauth/authorize
  ?client_id=<HUBSPOT_CLIENT_ID>
  &redirect_uri=<HUBSPOT_REDIRECT_URI>
  &scope=crm.objects.contacts.read%20automation
```

HubSpot will redirect to `/hubspot/callback` on your Lambda, which completes the OAuth token exchange automatically.

Required `.env` vars for the callback:

```env
HUBSPOT_CLIENT_ID=        # From your HubSpot app settings
HUBSPOT_CLIENT_SECRET=    # From your HubSpot app settings
HUBSPOT_REDIRECT_URI=     # Must match the redirect URI registered in your HubSpot app, e.g. https://xyz.execute-api.us-east-1.amazonaws.com/hubspot/callback
```

### Using the action in a workflow

1. Go to **HubSpot → Automations → Workflows**
2. Create a contact-based workflow
3. Add the **Send AI Sales Reply** action (under your app name)
4. Map the input fields:
   - **Contact Email** → Contact property: `Email`
   - **First Name** → Contact property: `First name`
   - **Last Name** → Contact property: `Last name`
   - **Inquiry / Message** → Contact property: `Message` (or any custom field)
5. Enroll contacts and test

---

## Future Extensions

The current agent handles the first touch — it receives a lead and sends one personalised reply. The natural next step is to close the loop on the full sales conversation:

- **Multi-turn follow-up** — track conversation history per lead and continue the email thread, answering follow-up questions automatically without human involvement
- **Lead qualification** — score replies based on intent signals (budget, timeline, urgency) and escalate hot leads to a human only when they are ready to close
- **Human handoff** — when the agent detects buying intent or a question it cannot confidently answer, notify a sales rep via Slack or CRM task rather than risking a bad reply
- **Reply parsing** — parse inbound email replies (via Gmail API or an inbound webhook) and feed them back into the agent to keep the conversation going
- **CRM enrichment** — write back conversation summaries, lead scores, and next-step notes directly into the CRM contact record after each exchange

The goal: the agent nurtures every lead from first contact to sales-ready, and only hands off to a human when it's time to close.

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
