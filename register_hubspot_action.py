"""One-time script to register the HubSpot custom workflow action.

Usage:
    python register_hubspot_action.py

Required .env vars:
    HUBSPOT_APP_ID          — from HubSpot app settings
    HUBSPOT_DEVELOPER_API_KEY — developer API key from developers.hubspot.com
    LAMBDA_URL              — base URL of the deployed Lambda, e.g.
                              https://b7r8or9qwk.execute-api.us-east-1.amazonaws.com
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

from hubspot_app import register_action

app_id        = os.environ["HUBSPOT_APP_ID"]
access_token  = os.environ["HUBSPOT_DEVELOPER_API_KEY"]
lambda_url    = os.environ["LAMBDA_URL"].rstrip("/")
definition_id = os.environ.get("HUBSPOT_DEFINITION_ID", "")
action_url    = f"{lambda_url}/hubspot/action"

print(f"{'Updating' if definition_id else 'Registering'} action for app {app_id}")
print(f"Action URL: {action_url}")

result = register_action(app_id, access_token, action_url, definition_id)
print("\nSuccess:")
print(json.dumps(result, indent=2))
