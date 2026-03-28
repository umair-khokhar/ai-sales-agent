"""Low-level utilities: LLM calls, email sending, HubSpot payload parsing."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import re

import httpx

GMI_API_KEY   = os.environ["GMI_API_KEY"]
GMI_BASE_URL  = "https://api.gmi-serving.com/v1"
GMI_MODEL     = "moonshotai/Kimi-K2-Instruct-0905"

GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_PASSWORD    = os.environ["GMAIL_PASSWORD"]
GMAIL_SENDER_NAME = os.environ.get("GMAIL_SENDER_NAME", GMAIL_USER)
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
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)   # **bold**, *italic*, ***both***
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text)      # _italic_, __bold__
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # ## headings
    text = re.sub(r'^\s*[-•]\s+', '- ', text, flags=re.MULTILINE)  # normalise bullets
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)   # numbered lists → plain
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # [text](url) → text
    text = re.sub(r'`(.+?)`', r'\1', text)                 # `code`
    return text.strip()


def _strip_signoff(text: str) -> str:
    """Remove any trailing sign-off the LLM may have added."""
    lines = text.rstrip().splitlines()
    # Walk backwards and drop lines that look like a sign-off
    cutoff = len(lines)
    for i in range(len(lines) - 1, max(len(lines) - 6, -1), -1):
        line = lines[i].strip()
        if not line:
            cutoff = i
            continue
        if any(kw in line for kw in [
            GMAIL_SENDER_NAME, AGENCY_NAME, AGENCY_TAGLINE,
            "Best regards", "Kind regards", "Warm regards",
            "Sincerely", "Cheers", "Thanks,", "Thank you,",
        ]):
            cutoff = i
        else:
            break
    return "\n".join(lines[:cutoff]).rstrip()


def _body_to_html(body: str) -> str:
    """Wrap plain-text email body in a branded agency HTML template."""
    plain = strip_markdown(_strip_signoff(body))

    agency_url_link      = f'<a href="{AGENCY_URL}" style="color:#ff6b35;text-decoration:none">{AGENCY_URL.replace("https://","").replace("http://","")}</a>' if AGENCY_URL else ""
    agency_calendar_dot  = "&nbsp;·&nbsp;" if AGENCY_URL and AGENCY_CALENDAR else ""
    agency_calendar_link = f'<a href="{AGENCY_CALENDAR}" style="color:#ff6b35;text-decoration:none">Book a Call</a>' if AGENCY_CALENDAR else ""
    agency_cta_button    = (
        f'<a href="{AGENCY_CALENDAR}" style="display:inline-block;background-color:#ff6b35;color:#ffffff;font-size:13px;font-weight:600;text-decoration:none;padding:10px 20px;border-radius:6px;white-space:nowrap">Book a Consultation →</a>'
        if AGENCY_CALENDAR else ""
    )

    # Convert newlines to HTML paragraphs
    paragraphs = [p.strip() for p in plain.split("\n\n") if p.strip()]
    html_paras = []
    for para in paragraphs:
        lines = para.split("\n")
        html_lines = []
        for line in lines:
            if line.startswith("- "):
                html_lines.append(f'<li style="margin-bottom:6px">{line[2:]}</li>')
            else:
                html_lines.append(line)
        # Wrap any <li> sequences in <ul>
        joined = "\n".join(html_lines)
        if "<li" in joined:
            joined = f'<ul style="margin:10px 0 10px 20px;padding:0">{joined}</ul>'
            html_paras.append(joined)
        else:
            html_paras.append(f'<p style="margin:0 0 16px 0">{joined}</p>')

    content_html = "\n".join(html_paras)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background-color:#F6F5F4;font-family:'Inter',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F6F5F4;padding:40px 20px">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

          <!-- Header -->
          <tr>
            <td style="background-color:#000000;padding:28px 40px;text-align:left">
              <span style="font-family:'Plus Jakarta Sans',Arial,sans-serif;font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">
                {AGENCY_NAME}
              </span>
              <span style="display:block;font-size:12px;color:#888888;margin-top:4px;font-weight:400">
                {AGENCY_TAGLINE}
              </span>
            </td>
          </tr>

          <!-- Orange accent bar -->
          <tr>
            <td style="background-color:#ff6b35;height:4px;font-size:0;line-height:0">&nbsp;</td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;color:#1a1a1a;font-size:15px;line-height:1.7">
              {content_html}
            </td>
          </tr>

          <!-- CTA divider -->
          <tr>
            <td style="padding:0 40px">
              <hr style="border:none;border-top:1px solid #f2f2f2;margin:0">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px 36px;background:#000000">
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td>
                    <p style="margin:0;font-size:14px;font-weight:600;color:#ffffff">
                      {GMAIL_SENDER_NAME}
                    </p>
                    <p style="margin:4px 0 0;font-size:13px;color:#888888">
                      {AGENCY_NAME} – {AGENCY_TAGLINE}
                    </p>
                    <p style="margin:12px 0 0;font-size:12px;color:#555555">
                      {agency_url_link}
                      {agency_calendar_dot}
                      {agency_calendar_link}
                    </p>
                  </td>
                  <td align="right" valign="middle">
                    {agency_cta_button}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email(to_addr: str, subject: str, body: str) -> None:
    plain_body = (
        f"{strip_markdown(_strip_signoff(body))}\n\n"
        f"--\n"
        f"{GMAIL_SENDER_NAME}\n"
        f"{AGENCY_NAME} – {AGENCY_TAGLINE}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Re: Your {AGENCY_NAME} Query — {subject}"
    msg["From"]    = f"{GMAIL_SENDER_NAME} <{GMAIL_USER}>"
    msg["To"]      = to_addr
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(_body_to_html(body), "html"))

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
        # check nested properties block first, then top-level flat keys
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
