import os
import random
import sqlite3
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot


TOKEN = os.environ["BOT_TOKEN"]

bot = telebot.TeleBot(TOKEN)

DB_FILE = "aura.db"


def get_db():
    return sqlite3.connect(DB_FILE, timeout=10)


# Создаём таблицу
db = get_db()
db.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    aura INTEGER DEFAULT 0,
    last_farm TEXT
)
""")
db.commit()
db.close()


@bot.message_handler(commands=["farm_aura"])
def farm_aura(message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "Игрок"
    today = str(date.today())

    db = get_db()

    try:
        user = db.execute(
            "SELECT aura, last_farm FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if user is None:
            aura = 0
            last_farm = None

            db.execute(
                "INSERT INTO users (user_id, name, aura, last_farm) VALUES (?, ?, ?, ?)",
                (user_id, name, 0, None)
            )
            db.commit()
        else:
            aura, last_farm = user

        if last_farm == today:
            bot.reply_to(
                message,
                "💀 Ты уже фармил ауру сегодня!\nПриходи завтра."
            )
            return

        gained = random.randint(-3, 10)
        new_aura = aura + gained

        db.execute(
            "UPDATE users SET name = ?, aura = ?, last_farm = ? WHERE user_id = ?",
            (name, new_aura, today, user_id)
        )
        db.commit()

    finally:
        db.close()

    if gained > 0:
        result = f"🔥 Ты получил +{gained} ауры!"
    elif gained == 0:
        result = "😐 Ты получил 0 ауры."
    else:
        result = f"💀 Ты потерял {abs(gained)} ауры!"

    bot.reply_to(
        message,
        f"{result}\n\n"
        f"✨ Твоя аура: {new_aura}"
    )


@bot.message_handler(commands=["rating"])
def rating(message):
    db = get_db()

    try:
        users = db.execute(
            "SELECT name, aura FROM users ORDER BY aura DESC LIMIT 10"
        ).fetchall()
    finally:
        db.close()

    if not users:
        bot.reply_to(message, "🏆 Рейтинг пока пуст!")
        return

    text = "🏆 РЕЙТИНГ АУРЫ\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, (name, aura) in enumerate(users, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."

        text += f"{medal} {name} — {aura} ауры"

        if i == 1:
            text += "\n   💀 ОН МОГГАЕТ ВСЕХ!"

        text += "\n"

    bot.reply_to(message, text)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Aura bot is alive!")

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


threading.Thread(target=start_web_server, daemon=True).start()

print("Aura bot запущен!")

bot.infinity_polling()
