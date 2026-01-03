import requests

requests.post(
    "https://api.pushover.net/1/messages.json",
    data={
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": "Test",
        "message": "Pushover fungerar 🎉",
    }
)
