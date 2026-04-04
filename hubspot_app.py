"""HubSpot Workflow Extension — action definition, signature verification, registration."""

import base64
import hashlib
import hmac
import os
import time

import httpx

HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET", "")

ACTION_DEFINITION = {
    "actionUrl": "",  # set at registration time
    "published": True,
    "objectTypes": ["CONTACT"],
    "inputFields": [
        {
            "typeDefinition": {"name": "email", "type": "string", "fieldType": "text"},
            "supportedValueTypes": ["OBJECT_PROPERTY"],
            "isRequired": True,
        },
        {
            "typeDefinition": {"name": "firstname", "type": "string", "fieldType": "text"},
            "supportedValueTypes": ["OBJECT_PROPERTY"],
            "isRequired": False,
        },
        {
            "typeDefinition": {"name": "lastname", "type": "string", "fieldType": "text"},
            "supportedValueTypes": ["OBJECT_PROPERTY"],
            "isRequired": False,
        },
        {
            "typeDefinition": {"name": "message", "type": "string", "fieldType": "text"},
            "supportedValueTypes": ["OBJECT_PROPERTY"],
            "isRequired": False,
        },
    ],
    "outputFields": [
        {
            "typeDefinition": {"name": "email_sent", "type": "string", "fieldType": "text"},
            "supportedValueTypes": ["STATIC_VALUE"],
        },
        {
            "typeDefinition": {"name": "draft", "type": "string", "fieldType": "text"},
            "supportedValueTypes": ["STATIC_VALUE"],
        },
    ],
    "labels": {
        "en": {
            "actionName": "Send AI Sales Reply",
            "actionDescription": "Drafts and sends a personalised sales reply using AI and your agency knowledge base.",
            "actionCardContent": "Send AI reply to {{email}}",
            "inputFieldLabels": {
                "email": "Contact Email",
                "firstname": "First Name",
                "lastname": "Last Name",
                "message": "Inquiry / Message",
            },
            "outputFieldLabels": {
                "email_sent": "Email Sent",
                "draft": "Email Draft",
            },
        }
    },
}


def verify_hubspot_signature(method: str, url: str, body: str, timestamp: str, signature: str) -> bool:
    """Verify X-HubSpot-Signature-v3.

    Args:
        method: HTTP method uppercase (e.g. 'POST')
        url: Full request URL including query string
        body: Raw request body as string
        timestamp: Value of X-HubSpot-Request-Timestamp header (ms since epoch)
        signature: Value of X-HubSpot-Signature-v3 header

    Returns True if valid and the request is not older than 5 minutes.
    """
    if not HUBSPOT_CLIENT_SECRET:
        return False

    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() * 1000 - ts) > 300_000:  # 5 minutes in ms
        return False

    source = f"{method}{url}{body}{timestamp}"
    expected = base64.b64encode(
        hmac.new(
            HUBSPOT_CLIENT_SECRET.encode(),
            source.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()

    return hmac.compare_digest(expected, signature)


def register_action(app_id: str, access_token: str, action_url: str, definition_id: str = "") -> dict:
    """Register or update the custom workflow action with HubSpot.

    access_token can be either:
    - A developer API key (UUID) → passed as hapikey query param
    - A portal OAuth access token (starts with 'pat-') → passed as Bearer token

    If definition_id is provided, PATCHes the existing action.
    Otherwise POSTs to create a new one.
    Returns the full API response dict.
    """
    definition = {**ACTION_DEFINITION, "actionUrl": action_url}

    import re
    is_developer_key = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", access_token))
    is_oauth_token = not is_developer_key
    if is_oauth_token:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}
        base_url = f"https://api.hubapi.com/automation/v4/actions/{app_id}"
    else:
        headers = {"Content-Type": "application/json"}
        base_url = f"https://api.hubapi.com/automation/v4/actions/{app_id}?hapikey={access_token}"

    if definition_id:
        url = base_url.replace(f"/actions/{app_id}", f"/actions/{app_id}/{definition_id}")
        with httpx.Client(timeout=15) as client:
            response = client.patch(url, json=definition, headers=headers)
    else:
        with httpx.Client(timeout=15) as client:
            response = client.post(base_url, json=definition, headers=headers)

    response.raise_for_status()
    return response.json()
