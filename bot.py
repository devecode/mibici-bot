import os
import httpx
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_BASE = os.getenv("API_BASE_URL", "http://localhost:3000")
DEFAULT_RADIUS = int(os.getenv("DEFAULT_RADIUS", "1200"))
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "5"))

ASK_RETURN_STATION_ID, ASK_RETURN_RESERVATION_ID = range(2)

CB_NEARBY = "NEARBY"
CB_RESERVE = "RESERVE"
CB_RETURN = "RETURN"
CB_MENU = "MENU"

async def api_get(path: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()

async def api_post(path: str, body: dict) -> (int, dict):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_BASE}{path}", json=body)
        try:
            data = r.json()
        except Exception:
            data = {"error": r.text}
        return r.status_code, data

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Ver estaciones cercanas", callback_data=CB_NEARBY)],
        [InlineKeyboardButton("🚲 Reservar bici (desde cercanas)", callback_data=CB_RESERVE)],
        [InlineKeyboardButton("↩️ Regresar bici", callback_data=CB_RETURN)],
    ])

def location_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Enviar ubicación", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def stations_buttons(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for s in items[:10]:
        sid = s["id"]
        bikes = s.get("available_bikes", 0)
        rows.append([InlineKeyboardButton(f"Reservar #{sid} (🚲{bikes})", callback_data=f"RESERVE:{sid}")])
    rows.append([InlineKeyboardButton("⬅️ Menú", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(rows)

def format_station(s: dict) -> str:
    dist = float(s.get("distance_m", 0))
    return (
        f"#{s['id']} - {s['name']}\n"
        f"🚲 bikes: {s.get('available_bikes')} | 🅿️ docks: {s.get('available_docks')}\n"
        f"📍 {round(dist, 1)} m | status: {s.get('status')}\n"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚲 MiBici Bot\nElige una opción:",
        reply_markup=main_menu_kb()
    )

async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Menú:", reply_markup=main_menu_kb())

async def nearby_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_location"] = "NEARBY"
    await q.edit_message_text("Compárteme tu ubicación 📍")
    await q.message.reply_text("Toca el botón:", reply_markup=location_kb())

async def reserve_flow_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_location"] = "RESERVE"
    await q.edit_message_text("Para reservar, primero compárteme tu ubicación 📍")
    await q.message.reply_text("Toca el botón:", reply_markup=location_kb())

async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("awaiting_location")
    if action not in ("NEARBY", "RESERVE"):
        return

    loc = update.message.location
    lat, lon = loc.latitude, loc.longitude

    await update.message.reply_text("Buscando estaciones cercanas...", reply_markup=ReplyKeyboardRemove())

    data = await api_get("/stations/nearby", {
        "lat": lat,
        "lon": lon,
        "radius": DEFAULT_RADIUS,
        "limit": DEFAULT_LIMIT,
        "onlyAvailable": "true",
    })

    items = data.get("items", [])
    if not items:
        await update.message.reply_text(
            f"No encontré estaciones con bicis disponibles en {DEFAULT_RADIUS}m.\n\nMenú:",
            reply_markup=main_menu_kb()
        )
        context.user_data.pop("awaiting_location", None)
        return

    msg = "Estas son las más cercanas:\n\n" + "\n".join(format_station(s) for s in items)
    await update.message.reply_text(msg, reply_markup=stations_buttons(items))

    context.user_data.pop("awaiting_location", None)

async def reserve_station_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    station_id = int(q.data.split(":")[1])

    status, res = await api_post(f"/stations/{station_id}/reserve", {"userId": str(user_id)})

    if status == 200 and res.get("ok") is True:
        reservation_id = res["reservation"]["id"]
        await q.edit_message_text(
            f"✅ Reservada en estación #{station_id}\n"
            f"reservationId:\n{reservation_id}\n\n"
            f"Inventario ahora: bikes={res['inventory']['available_bikes']} docks={res['inventory']['available_docks']}\n\n"
            f"⚠️ Guarda tu reservationId, lo necesitarás para regresar.\n\nMenú:",
            reply_markup=main_menu_kb()
        )
    else:
        await q.edit_message_text(
            f"⚠️ No se pudo reservar: {res.get('error', 'UNKNOWN')}\n\nMenú:",
            reply_markup=main_menu_kb()
        )

async def return_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "↩️ Regresar bici\n\n"
        "Paso 1/2: Envíame el stationId donde vas a regresar (ej. 57)."
    )
    return ASK_RETURN_STATION_ID

async def return_station_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    try:
        station_id = int(text)
        if station_id <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("stationId inválido. Envíame un número entero (ej. 57).")
        return ASK_RETURN_STATION_ID

    context.user_data["return_station_id"] = station_id
    await update.message.reply_text(
        "Paso 2/2: Envíame el reservationId (UUID) que te regresó el endpoint /reserve."
    )
    return ASK_RETURN_RESERVATION_ID

async def return_reservation_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reservation_id = (update.message.text or "").strip()
    station_id = context.user_data.get("return_station_id")

    if not reservation_id:
        await update.message.reply_text("reservationId vacío. Pégalo tal cual.")
        return ASK_RETURN_RESERVATION_ID

    status, res = await api_post(
        f"/stations/{station_id}/return",
        {"userId": str(user_id), "reservationId": reservation_id}
    )

    if status == 200 and res.get("ok") is True:
        await update.message.reply_text(
            f"✅ Bici devuelta en estación #{station_id}\n"
            f"Reserva: {res['reservation']['id']} status={res['reservation']['status']}\n"
            f"Inventario ahora: bikes={res['inventory']['available_bikes']} docks={res['inventory']['available_docks']}\n\n"
            f"Menú:",
            reply_markup=main_menu_kb()
        )
    else:
        await update.message.reply_text(
            f"⚠️ No se pudo regresar: {res.get('error', 'UNKNOWN')}\n\nMenú:",
            reply_markup=main_menu_kb()
        )

    context.user_data.pop("return_station_id", None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.\n\nMenú:", reply_markup=main_menu_kb())
    return ConversationHandler.END

def main():
    if not TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en .env")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(menu_cb, pattern=f"^{CB_MENU}$"))
    app.add_handler(CallbackQueryHandler(nearby_cb, pattern=f"^{CB_NEARBY}$"))
    app.add_handler(CallbackQueryHandler(reserve_flow_cb, pattern=f"^{CB_RESERVE}$"))

    app.add_handler(CallbackQueryHandler(reserve_station_cb, pattern=r"^RESERVE:\d+$"))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))

    return_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(return_start_cb, pattern=f"^{CB_RETURN}$")],
        states={
            ASK_RETURN_STATION_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, return_station_id)],
            ASK_RETURN_RESERVATION_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, return_reservation_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(return_conv)

    app.run_polling()

if __name__ == "__main__":
    main()
