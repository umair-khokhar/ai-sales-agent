"""
HubBase AI Agent — entry point.

Flow:
  POST /hubspot-webhook  ← HubSpot sends new contact/form submission
      │
      ├─ parse lead (name, email, message)       [utils.py]
      ├─ extract search queries via Kimi         [helpers.py]
      ├─ recall context from HydraDB             [helpers.py]
      ├─ draft reply email via Kimi              [routes.py]
      └─ send email to lead via Gmail SMTP       [utils.py]

POST /webhook  ← generic chat endpoint
GET  /health
"""

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from routes import app

if __name__ == "__main__":
    uvicorn.run("routes:app", host="0.0.0.0", port=3000, reload=True)
