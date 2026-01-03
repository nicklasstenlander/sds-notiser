import os
import json
import time
from datetime import datetime
import requests

ORG = os.getenv("COGWORK_ORG", "sollentunadans")
PW = os.getenv("COGWORK_PW", "")  # ni har ingen pw just nu
COGWORK_BASE = os.getenv("COGWORK_BASE", "https://dans.se/api/public")

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")

STATE_FILE = "state.json"

# Hur många notiser max per körning (skydd mot spam om många nya)
MAX_NOTIFICATIONS_PER_RUN = int(os.getenv("MAX_NOTIFICATIONS_PER_RUN", "5"))

# Hur många bokningar vi hämtar varje körning (behöver vara > MAX_NOTIFICATIONS_PER_RUN)
FETCH_MAX_ROWS = int(os.getenv("FETCH_MAX_ROWS", "25"))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_notified_booking_id": 0}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_notified_booking_id": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def pushover_send(title: str, message: str):
    if not PUSHOVER_APP_TOKEN or not PUSHOVER_USER_KEY:
        raise RuntimeError("Missing PUSHOVER_APP_TOKEN or PUSHOVER_USER_KEY (GitHub Secrets).")

    payload = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
    }
    r = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=30)
    # Ge lite bättre felmeddelande om något går fel
    if r.status_code >= 400:
        raise RuntimeError(f"Pushover error {r.status_code}: {r.text}")
    return r.json()


def fetch_latest_bookings(max_rows: int):
    # Vi tar alltid senaste bokningarna via maxRows=... (API verkar returnera nyast först i era tester)
    url = f"{COGWORK_BASE}/bookings/?org={ORG}&pw={PW}&maxRows={max_rows}&verbose=1"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    if "errors" in data and data["errors"]:
        raise RuntimeError(f"CogWork API errors: {data['errors']}")

    return data.get("bookings", [])

def format_booking_message(b):
    event = b.get("event", {}) or {}
    participant = b.get("participant", {}) or {}
    payment = b.get("payment", {}) or {}

    event_name = event.get("name", "Okänd kurs")
    event_code = event.get("code", "")
    start_dt = event.get("startDateTime") or (
        f"{event.get('startDate','')} {event.get('startTime','')}".strip()
    )

    participant_name = participant.get("name", "Okänd deltagare")
    status_name = (b.get("status", {}) or {}).get("name", "")
    created = b.get("created", "")  # ← viktigt för “senaste bokningen”

    # Payment
    paid = payment.get("paid")
    amount_paid = payment.get("amountPaid")
    price = payment.get("priceAgreed")
    currency = payment.get("currency", "SEK")
    due = payment.get("paymentDue")

    # Payment strings
    if paid is True:
        paid_str = "✅ Betald"
        if amount_paid is not None:
            paid_str += f" ({amount_paid} {currency})"
    elif paid is False:
        paid_str = "⏳ Ej betald"
        if due:
            paid_str += f" (förfallo {due})"
    else:
        paid_str = "❓ Betalstatus okänd"

    price_str = f"💰 Pris: {price} {currency}" if price is not None else None

    lines = [
        f"{event_name}",
        f"Elev: {participant_name}",
        f"Status: {status_name}",
    ]

    if start_dt:
        lines.append(f"Start: {start_dt}")
    if event_code:
        lines.append(f"Kod: {event_code}")
    if price_str:
        lines.append(price_str)

    lines.append(paid_str)

    if created:
        lines.append(f"🕒 Skapad: {created}")

    return "\n".join([line for line in lines if line.strip()])


def main():
    state = load_state()
    last_id = int(state.get("last_notified_booking_id", 0))

    print(f"Loaded state: last_notified_booking_id={last_id}")

    bookings = fetch_latest_bookings(FETCH_MAX_ROWS)
    print(f"Fetched {len(bookings)} bookings")

    # Plocka ut de som är "nya" jämfört med vår state.
    # OBS: era booking.id är numeriska och växer.
    new_bookings = []
    for b in bookings:
        try:
            bid = int(b.get("id", 0))
        except (TypeError, ValueError):
            continue
        if bid > last_id:
            new_bookings.append(b)

    if not new_bookings:
        print("No new bookings. Nothing to notify.")
        return

    # Sortera gamla->nya så notiserna kommer i rätt ordning
    new_bookings.sort(key=lambda x: int(x.get("id", 0)))

    # Begränsa antal notiser per körning (anti-spam)
    to_notify = new_bookings[:MAX_NOTIFICATIONS_PER_RUN]
    remaining = len(new_bookings) - len(to_notify)

    print(f"New bookings found: {len(new_bookings)}. Will notify: {len(to_notify)} (remaining: {remaining})")

    # Skicka notiser
    for b in to_notify:
        bid = int(b.get("id", 0))
        title = "Ny anmälan"
        message = format_booking_message(b)
        print(f"Sending notification for booking id={bid} ...")
        pushover_send(title, message)
        # liten paus för att vara snäll mot Pushover
        time.sleep(0.5)

    # Uppdatera state till högsta id vi sett (även om vi inte hann notifiera alla)
    # så riskerar vi inte spam nästa körning. Vill du hellre notifiera "ikapp" kan vi ändra.
    max_seen_id = max(int(b.get("id", 0)) for b in new_bookings)
    state["last_notified_booking_id"] = max_seen_id
    state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    save_state(state)

    print(f"Updated state last_notified_booking_id={max_seen_id}")
    if remaining > 0:
        print(f"Note: {remaining} more new bookings existed, but were skipped due to MAX_NOTIFICATIONS_PER_RUN.")


if __name__ == "__main__":
    main()
