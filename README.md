# MiBici Telegram Bot (Nearby / Reserve / Return)

A Telegram bot that integrates with a REST API to:
- 📍 Fetch nearby bike stations based on the user’s location
- 🚲 Reserve a bike at a selected station
- ↩️ Return a bike using `stationId` + `reservationId`

The bot uses **python-telegram-bot** (async) and **httpx** to call the API.

---

## Features

- **Main menu** with inline buttons:
  - **View nearby stations**
  - **Reserve bike (from nearby results)**
  - **Return bike (guided 2-step flow)**
- **Location request keyboard** (Telegram “Send location” button)
- Lists up to **10 stations** as “Reserve #ID” buttons
- Reservation returns a **reservationId (UUID)** that the user must keep to return the bike
- Return flow implemented using a **ConversationHandler**

---

## Requirements

- Python **3.10+** (recommended)
- A Telegram Bot Token from **@BotFather**
- A running API that exposes these endpoints:

### API Endpoints Used

**GET** `/stations/nearby`  
Query params:
- `lat` (float)
- `lon` (float)
- `radius` (int, meters)
- `limit` (int)
- `onlyAvailable` ("true" / "false")

Expected response shape (example):
```json
{
  "items": [
    {
      "id": 57,
      "name": "Station Name",
      "available_bikes": 3,
      "available_docks": 12,
      "status": "ACTIVE",
      "distance_m": 245.6
    }
  ]
}
````

**POST** `/stations/{stationId}/reserve`
Body:

```json
{ "userId": "123456789" }
```

Expected response shape (success):

```json
{
  "ok": true,
  "reservation": { "id": "UUID", "status": "reserved" },
  "inventory": { "available_bikes": 2, "available_docks": 13 }
}
```

**POST** `/stations/{stationId}/return`
Body:

```json
{ "userId": "123456789", "reservationId": "UUID" }
```

Expected response shape (success):

```json
{
  "ok": true,
  "reservation": { "id": "UUID", "status": "returned" },
  "inventory": { "available_bikes": 3, "available_docks": 12 }
}
```

On error, the bot expects something like:

```json
{ "error": "REASON_CODE_OR_MESSAGE" }
```

---

## Installation

### 1) Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
```

### 2) Install dependencies

```bash
pip install -U python-telegram-bot httpx python-dotenv
```

---

## Configuration (.env)

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
API_BASE_URL=http://localhost:3000
DEFAULT_RADIUS=1200
DEFAULT_LIMIT=5
```

### Env vars

* `TELEGRAM_BOT_TOKEN` (**required**): Telegram bot token
* `API_BASE_URL` (default: `http://localhost:3000`): Base URL for the REST API
* `DEFAULT_RADIUS` (default: `1200`): Search radius in meters
* `DEFAULT_LIMIT` (default: `5`): Max stations returned by the API (bot also limits buttons to 10)

---

## Run

```bash
python bot.py
```

The bot runs in **polling mode**:

```py
app.run_polling()
```

---

## Usage (User Flow)

### Start

* User sends `/start`
* Bot shows the main menu

### Nearby Stations

1. Tap **📍 Ver estaciones cercanas**
2. Bot asks for location
3. User taps **📍 Enviar ubicación**
4. Bot calls:

   * `GET /stations/nearby`
5. Bot replies with:

   * A formatted list of stations
   * Inline buttons to reserve a specific station

### Reserve

1. From nearby results, tap **Reservar #ID**
2. Bot calls:

   * `POST /stations/{ID}/reserve` with `{ userId }`
3. On success, bot displays:

   * `reservationId` (UUID)
   * updated station inventory
4. User must save `reservationId` for returning

### Return

1. Tap **↩️ Regresar bici**
2. Step 1/2: User sends the `stationId`
3. Step 2/2: User sends the `reservationId`
4. Bot calls:

   * `POST /stations/{stationId}/return` with `{ userId, reservationId }`
5. Bot confirms success and shows updated inventory

To cancel the return flow at any time:

* Send `/cancel`

---

## Project Structure (suggested)

```
.
├── bot.py
├── .env
└── README.md
```

---

## Notes / Implementation Details

* The bot stores temporary state in `context.user_data`, e.g.:

  * `"awaiting_location"`: `"NEARBY"` or `"RESERVE"`
  * `"return_station_id"`: station id during the return flow
* Nearby/reserve location flow uses `MessageHandler(filters.LOCATION, on_location)`
* The return process uses a `ConversationHandler` with two steps:

  * `ASK_RETURN_STATION_ID`
  * `ASK_RETURN_RESERVATION_ID`

---

## Troubleshooting

### Missing token

If you see:
`RuntimeError: Falta TELEGRAM_BOT_TOKEN en .env`

Make sure `.env` exists and contains `TELEGRAM_BOT_TOKEN`.

### API not reachable

* Confirm `API_BASE_URL` is correct
* Confirm the server is running
* Test with curl:

```bash
curl "http://localhost:3000/stations/nearby?lat=20.67&lon=-103.35&radius=1200&limit=5&onlyAvailable=true"
```

### Telegram location button not showing

* Ensure you’re using the “📍 Enviar ubicación” button
* Some Telegram clients require the user to grant location permissions


