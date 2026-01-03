import os
import json
import requests
from datetime import datetime, timedelta
import pytz

ORG = "sollentunadans"
BASE = "https://dans.se/api/public"

STATE_FILE = "booking_state.json"

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN", "")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")

TZ = pytz.timezone("Europe/Stockholm")


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_created": None, "last_id": None}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def parse_created(dt_str: str) -> datetime:
    # API-format: "YYYY-MM-DD HH:MM:SS"
    return TZ.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S"))


def fetch_latest_bookings(max_rows=25):
    url = f"{BASE}/bookings/?org={ORG}&maxRows={max_rows}&verbose=1"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("bookings", [])


def pushover_send(message: str, title: str = "Ny anmälan"):
    if not (PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY):
        raise RuntimeError("Missing PUSHOVER_APP_TOKEN or PUSHOVER_USER_KEY env vars.")

    r = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": PUSHOVER_APP_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "title": title,
            "message": message,
        },
        timeout=30,
    )
    r.raise_for_status()


def format_booking(b):
    created = b.get("created", "")
    bid = b.get("id", "")
    event = b.get("event", {}) or {}
    participant = b.get("participant", {}) or {}
    payment = b.get("payment", {}) or {}

    event_name = event.get("name", "")
    event_code = event.get("code", "")
    start_dt = event.get("startDateTime", "")
    participant_name = participant.get("name", "")
    paid = payment.get("paid", False)
    amount = payment.get("amountPaid") or payment.get("priceAgreed")

    paid_txt = "Betald" if paid else "Ej betald"
    amount_txt = f"{amount} SEK" if amount is not None else ""

    # Kort och tydligt i push
    msg = (
        f"{participant_name}\n"
        f"{event_name} ({event_code})\n"
        f"Start: {start_dt}\n"
        f"{paid_txt} {amount_txt}\n"
        f"Skapad: {created} (ID {bid})"
    )
    return msg


def main():
    state = load_state()

    # Om vi aldrig kört: sätt en “cutoff” bakåt i tiden så vi inte spammar
    if not state["last_created"]:
        cutoff = datetime.now(TZ) - timedelta(minutes=10)
    else:
        cutoff = parse_created(state["last_created"])

    bookings = fetch_latest_bookings(max_rows=50)

    # Filtrera "nya"
    new = []
    for b in bookings:
        c = b.get("created")
        if not c:
            continue
        created_dt = parse_created(c)
        if created_dt > cutoff:
            new.append((created_dt, b))

    # Sortera äldst -> nyast så pusharna kommer i ordning
    new.sort(key=lambda x: x[0])

    if not new:
        print("No new bookings.")
        return

    # Skicka push per booking (eller batcha, om du vill)
    newest_created_dt = None
    newest_id = None

    for created_dt, b in new:
        pushover_send(format_booking(b), title="Ny anmälan (CogWork)")
        newest_created_dt = created_dt
        newest_id = b.get("id")

    # Uppdatera state till senaste vi hanterat
    if newest_created_dt:
        state["last_created"] = newest_created_dt.strftime("%Y-%m-%d %H:%M:%S")
        state["last_id"] = newest_id
        save_state(state)

    print(f"Sent {len(new)} notifications. Updated state to {state['last_created']}.")


if __name__ == "__main__":
    main()
