"""FastAPI route definitions."""

import json
import logging
import os
from fastapi import Depends, FastAPI, HTTPException, Query, Request

logger = logging.getLogger(__name__)
from mangum import Mangum
from pydantic import BaseModel

from helpers import extract_queries, recall_context, TENANT_ID
from hubspot_app import verify_hubspot_signature
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

Write a short, warm reply email. Keep it under 100 words total.
- Address the prospect by first name
- One sentence answering their question using the context
- One sentence inviting them to book a call{f": {AGENCY_CALENDAR}" if AGENCY_CALENDAR else ""}
- End with 1 short qualifying question (timeline or budget)
- Do NOT include a sign-off or signature — it will be added automatically

Prospect name: {{name}}
Prospect email: {{email}}
Prospect inquiry: {{inquiry}}

Context from {AGENCY_NAME} website:
{{context}}

Return only the email body (no Subject line, no sign-off).
Plain text only — no markdown or asterisks. Use a hyphen (-) for any bullet points."""

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_spam_or_sales_pitch(inquiry: str) -> bool:
    """Return True if the inquiry is spam or a vendor sales pitch."""
    result = call_gmi(
        "You are a spam classifier. Reply with only YES or NO.",
        f"Is the following message spam or an attempt to sell a product/service to us? "
        f"Reply YES if it's spam, a sales pitch, a vendor offer, or unsolicited promotion. "
        f"Reply NO if it's a genuine inbound inquiry from a potential customer.\n\nMessage: {inquiry}",
    ).strip().upper()
    return result.startswith("YES")

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

    if is_spam_or_sales_pitch(inquiry):
        logger.info("Ignored spam/sales-pitch from %s", email)
        return HubSpotWebhookResponse(lead_email=email, email_sent=False, draft="[ignored: spam or sales pitch]")

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


@app.post("/hubspot/action")
async def hubspot_action(request: Request):
    body_bytes = await request.body()
    body_str   = body_bytes.decode()

    sig       = request.headers.get("X-HubSpot-Signature-v3", "")
    timestamp = request.headers.get("X-HubSpot-Request-Timestamp", "")
    lambda_url = os.environ.get("LAMBDA_URL", "").rstrip("/")
    url       = f"{lambda_url}/hubspot/action" if lambda_url else str(request.url)

    if not verify_hubspot_signature("POST", url, body_str, timestamp, sig):
        raise HTTPException(status_code=400, detail="Invalid or expired HubSpot signature")

    payload     = json.loads(body_str)
    input_fields = payload.get("inputFields", {})

    email    = input_fields.get("email", "")
    name     = " ".join(filter(None, [input_fields.get("firstname", ""), input_fields.get("lastname", "")])) or "there"
    inquiry  = input_fields.get("message", "integration services and pricing")

    if not email:
        raise HTTPException(status_code=400, detail="email is required in inputFields")

    if is_spam_or_sales_pitch(inquiry):
        logger.info("Ignored spam/sales-pitch from %s", email)
        return {"outputFields": {"email_sent": "false", "draft": "[ignored: spam or sales pitch]"}}

    queries          = extract_queries(inquiry)
    context, _       = recall_context(queries, top_k=10)

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

    return {"outputFields": {"email_sent": str(email_sent).lower(), "draft": draft}}


@app.get("/hubspot/callback")
async def hubspot_oauth_callback(code: str = Query(...)):
    """OAuth callback — exchanges the HubSpot authorization code for an access token."""
    client_id     = os.environ.get("HUBSPOT_CLIENT_ID", "")
    client_secret = os.environ.get("HUBSPOT_CLIENT_SECRET", "")
    redirect_uri  = os.environ.get("HUBSPOT_REDIRECT_URI", "http://localhost:3000/hubspot/callback")

    if not all([client_id, client_secret]):
        raise HTTPException(status_code=500, detail="Missing HUBSPOT_CLIENT_ID or HUBSPOT_CLIENT_SECRET env vars")

    import httpx

    token_resp = httpx.post(
        "https://api.hubapi.com/oauth/v1/token",
        data={
            "grant_type":    "authorization_code",
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "code":          code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {token_resp.text}")

    logger.info("OAuth install complete for portal.")
    return {"status": "ok", "message": "App installed successfully."}


@app.get("/health")
async def health():
    return {"status": "ok", "tenant": TENANT_ID, "model": GMI_MODEL}


# Lambda handler (used by AWS Lambda; ignored when running locally via uvicorn)
handler = Mangum(app, lifespan="off")
