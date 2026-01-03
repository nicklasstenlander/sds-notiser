import os
import requests

PUSHOVER_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")

if not PUSHOVER_APP_TOKEN or not PUSHOVER_USER_KEY:
    raise SystemExit("Missing PUSHOVER_APP_TOKEN or PUSHOVER_USER_KEY (GitHub Secrets).")

payload = {
    "token": PUSHOVER_APP_TOKEN,
    "user": PUSHOVER_USER_KEY,
    "title": "SODSS – test",
    "message": "Pushover funkar ✅ (skickat från GitHub Actions)"
}

r = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=20)
print("Status:", r.status_code)
print("Response:", r.text)
r.raise_for_status()
