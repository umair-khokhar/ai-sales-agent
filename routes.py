"""FastAPI route definitions."""

import logging
import os
from fastapi import Depends, FastAPI, HTTPException, Query, Request

logger = logging.getLogger(__name__)
from mangum import Mangum
from pydantic import BaseModel

from helpers import extract_queries, recall_context, TENANT_ID
from utils import call_gmi, send_email, parse_hubspot_contact, GMI_MODEL, AGENCY_NAME, AGENCY_URL, AGENCY_TAGLINE, AGENCY_CALENDAR

app = FastAPI(title="AI Sales Agent")

# ── Auth ──────────────────────────────────────────────────────────────────────
_API_KEY = os.environ.get("API_KEY", "")

def require_api_key(api_key: str = Query(..., alias="api_key")):
    if not _API_KEY or api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# ── Prompts ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are a sales assistant for {AGENCY_NAME} ({AGENCY_URL}), a {AGENCY_TAGLINE}.
Answer questions using only the provided context from the agency website.
If the context doesn't contain enough information, say so honestly.
Be concise and direct."""

EMAIL_DRAFT_PROMPT = f"""You are a professional sales rep at {AGENCY_NAME} ({AGENCY_URL}), a {AGENCY_TAGLINE}.

Write a warm, professional reply email to a prospect based on the context below.
- Address the prospect by first name
- Answer their specific question using the context
- Include relevant pricing ranges if available in the context
- End with 2-3 short follow-up questions to better understand their needs (timeline, budget, current setup, or scale) — keep them conversational, not like a form
- Do NOT include a sign-off or signature — it will be added automatically

Prospect name: {{name}}
Prospect email: {{email}}
Prospect inquiry: {{inquiry}}

Context from {AGENCY_NAME} website:
{{context}}

Return only the email body (no Subject line, no sign-off).
Write in plain text only — no markdown, no asterisks for bold, no bullet symbols, no numbered lists.
Use short paragraphs separated by blank lines."""

# ── Schemas ───────────────────────────────────────────────────────────────────
class WebhookRequest(BaseModel):
    message: str
    top_k: int = 5

class WebhookResponse(BaseModel):
    answer: str
    sources: list[str]
    model: str

class HubSpotWebhookResponse(BaseModel):
    lead_email: str
    email_sent: bool
    draft: str

# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/hubspot-webhook", response_model=HubSpotWebhookResponse, dependencies=[Depends(require_api_key)])
async def hubspot_webhook(request: Request):
    payload = await request.json()
    name, email, inquiry = parse_hubspot_contact(payload)
    if not email:
        raise HTTPException(status_code=400, detail=f"No email found in HubSpot payload. Keys received: {list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__}")

    queries          = extract_queries(inquiry)
    context, sources = recall_context(queries, top_k=10)

    draft = call_gmi("", EMAIL_DRAFT_PROMPT.format(
        name=name, email=email, inquiry=inquiry, context=context,
    ))

    subject = call_gmi(
        "",
        f"Write a concise, professional email subject line (max 10 words) for this inquiry: {inquiry}\nReturn only the subject line.",
    ).strip().strip('"')

    email_sent = False
    try:
        send_email(email, subject, draft)
        email_sent = True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", email, e)

    return HubSpotWebhookResponse(lead_email=email, email_sent=email_sent, draft=draft)


@app.post("/webhook", response_model=WebhookResponse, dependencies=[Depends(require_api_key)])
async def webhook(req: WebhookRequest):
    try:
        queries          = extract_queries(req.message)
        context, sources = recall_context(queries, req.top_k)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HydraDB error: {e}")

    try:
        answer = call_gmi(SYSTEM_PROMPT, f"Context:\n{context}\n\nQuestion: {req.message}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GMI error: {e}")

    return WebhookResponse(answer=answer, sources=sources, model=GMI_MODEL)


@app.get("/health")
async def health():
    return {"status": "ok", "tenant": TENANT_ID, "model": GMI_MODEL}


# Lambda handler (used by AWS Lambda; ignored when running locally via uvicorn)
handler = Mangum(app, lifespan="off")
