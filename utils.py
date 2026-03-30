"""Low-level utilities: LLM calls, email sending, HubSpot payload parsing."""

import os
import re
import smtplib
from email.mime.text import MIMEText
from typing import Any

import httpx

GMI_API_KEY   = os.environ["GMI_API_KEY"]
GMI_BASE_URL  = "https://api.gmi-serving.com/v1"
GMI_MODEL     = "moonshotai/Kimi-K2-Instruct-0905"

GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_PASSWORD    = os.environ["GMAIL_PASSWORD"]
GMAIL_SENDER_NAME = os.environ.get("GMAIL_SENDER_NAME", GMAIL_USER)
GMAIL_SIGNATURE   = os.environ.get("GMAIL_SIGNATURE", "").replace("\\n", "\n")
GMAIL_SMTP        = "smtp.gmail.com"
GMAIL_PORT        = 587

# Agency branding (all configurable via .env)
AGENCY_NAME     = os.environ.get("AGENCY_NAME", "Our Agency")
AGENCY_URL      = os.environ.get("AGENCY_URL", "")
AGENCY_TAGLINE  = os.environ.get("AGENCY_TAGLINE", "HubSpot Partner")
AGENCY_CALENDAR = os.environ.get("AGENCY_CALENDAR_URL", "")


def call_gmi(system: str, user: str) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    resp = httpx.post(
        f"{GMI_BASE_URL}/chat/completions",
        json={"model": GMI_MODEL, "messages": messages, "max_tokens": 1024, "temperature": 0.3},
        headers={"Authorization": f"Bearer {GMI_API_KEY}", "Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def strip_markdown(text: str) -> str:
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-•]\s+', '- ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text.strip()


def send_email(to_addr: str, subject: str, body: str) -> None:
    plain = strip_markdown(body)
    if GMAIL_SIGNATURE:
        plain = f"{plain}\n\n{GMAIL_SIGNATURE}"
    msg = MIMEText(plain, "plain")
    msg["Subject"] = f"Re: Your {AGENCY_NAME} Query — {subject}"
    msg["From"]    = f"{GMAIL_SENDER_NAME} <{GMAIL_USER}>"
    msg["To"]      = to_addr

    with smtplib.SMTP(GMAIL_SMTP, GMAIL_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, to_addr, msg.as_string())


def parse_hubspot_contact(payload: Any) -> tuple[str, str, str]:
    """
    Extract (name, email, inquiry) from HubSpot webhook payload.

    Handles all common HubSpot webhook shapes:
    - Workflow action:  {"objectId": 123, "properties": {"email": "..."}}
    - Workflow flat:    {"email": "...", "firstname": "..."}  (no properties wrapper)
    - Subscription:     [{"objectId": 123, ...}]
    - Nested value:     {"properties": {"email": {"value": "..."}}}
    """
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    nested = payload.get("properties", {})

    def _val(v: Any) -> str:
        if isinstance(v, dict):
            return str(v.get("value", "") or "")
        return str(v) if v else ""

    def prop(key: str) -> str:
        return _val(nested.get(key)) or _val(payload.get(key))

    firstname = prop("firstname")
    lastname  = prop("lastname")
    name      = f"{firstname} {lastname}".strip() or "there"
    email     = prop("email")
    inquiry   = (
        prop("message")
        or prop("content")
        or prop("subject")
        or prop("hs_content_membership_notes")
        or "integration services and pricing"
    )
    return name, email, inquiry
