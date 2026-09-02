import os
import random
import sqlite3
from datetime import date

import telebot

TOKEN = os.environ["BOT_TOKEN"]

bot = telebot.TeleBot(TOKEN)

db = sqlite3.connect("aura.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    aura INTEGER DEFAULT 0,
    last_farm TEXT
)
""")
db.commit()


@bot.message_handler(commands=["farm_aura"])
def farm_aura(message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "Игрок"
    today = str(date.today())

    cursor.execute(
        "SELECT aura, last_farm FROM users WHERE user_id = ?",
        (user_id,)
    )
    user = cursor.fetchone()

    if user is None:
        aura = 0
        last_farm = None
        cursor.execute(
            "INSERT INTO users (user_id, name, aura, last_farm) VALUES (?, ?, ?, ?)",
            (user_id, name, 0, None)
        )
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

    cursor.execute(
        "UPDATE users SET name = ?, aura = ?, last_farm = ? WHERE user_id = ?",
        (name, new_aura, today, user_id)
    )
    db.commit()

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
    cursor.execute(
        "SELECT name, aura FROM users ORDER BY aura DESC LIMIT 10"
    )
    users = cursor.fetchall()

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


print("Aura bot запущен!")
bot.infinity_polling()
