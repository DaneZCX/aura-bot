import os
import random
import sqlite3
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import telebot


# =========================
# CONFIG
# =========================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в переменных окружения!")

DB_FILE = os.environ.get("DB_FILE", "aura.db")

bot = telebot.TeleBot(TOKEN)


# =========================
# DATABASE
# =========================

def get_db():
    """
    Новое SQLite-соединение на каждый запрос.
    Это безопаснее при работе из нескольких потоков.
    """
    db = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False
    )

    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")

    return db


def init_db():
    db = get_db()

    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                aura INTEGER DEFAULT 0,
                last_farm TEXT
            )
        """)

        db.commit()

    finally:
        db.close()


# =========================
# /farm_aura
# =========================

@bot.message_handler(commands=["farm_aura"])
def farm_aura(message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "Игрок"
    today = date.today().isoformat()

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
                """
                INSERT INTO users (user_id, name, aura, last_farm)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, name, aura, last_farm)
            )

            db.commit()

        else:
            aura, last_farm = user

            # Обновляем имя пользователя
            db.execute(
                "UPDATE users SET name = ? WHERE user_id = ?",
                (name, user_id)
            )

            db.commit()

        if last_farm == today:
            bot.reply_to(
                message,
                "💀 Ты уже фармил ауру сегодня!\n"
                "Приходи завтра."
            )
            return

        gained = random.randint(-3, 10)
        new_aura = aura + gained

        db.execute(
            """
            UPDATE users
            SET name = ?, aura = ?, last_farm = ?
            WHERE user_id = ?
            """,
            (name, new_aura, today, user_id)
        )

        db.commit()

    except sqlite3.Error as e:
        print(f"[DB ERROR] /farm_aura: {e}")

        try:
            bot.reply_to(
                message,
                "⚠️ Не удалось сохранить ауру. Попробуй ещё раз."
            )
        except Exception as reply_error:
            print(f"[TELEGRAM ERROR] {reply_error}")

        return

    finally:
        db.close()

    if gained > 0:
        result = f"🔥 Ты получил +{gained} ауры!"
    elif gained == 0:
        result = "😐 Ты получил 0 ауры."
    else:
        result = f"💀 Ты потерял {abs(gained)} ауры!"

    try:
        bot.reply_to(
            message,
            f"{result}\n\n"
            f"✨ Твоя аура: {new_aura}"
        )
    except Exception as e:
        print(f"[TELEGRAM ERROR] /farm_aura reply: {e}")


# =========================
# /rating
# =========================

@bot.message_handler(commands=["rating"])
def rating(message):
    db = get_db()

    try:
        users = db.execute(
            """
            SELECT name, aura
            FROM users
            ORDER BY aura DESC
            LIMIT 10
            """
        ).fetchall()

    except sqlite3.Error as e:
        print(f"[DB ERROR] /rating: {e}")

        try:
            bot.reply_to(
                message,
                "⚠️ Не удалось загрузить рейтинг."
            )
        except Exception as reply_error:
            print(f"[TELEGRAM ERROR] {reply_error}")

        return

    finally:
        db.close()

    if not users:
        bot.reply_to(
            message,
            "🏆 Рейтинг пока пуст!"
        )
        return

    text = "🏆 РЕЙТИНГ АУРЫ\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, (name, aura) in enumerate(users, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."

        text += f"{medal} {name} — {aura} ауры"

        if i == 1:
            text += "\n   💀 ОН МОГГАЕТ ВСЕХ!"

        text += "\n"

    try:
        bot.reply_to(message, text)
    except Exception as e:
        print(f"[TELEGRAM ERROR] /rating reply: {e}")


# =========================
# WEB SERVER
# =========================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

        self.wfile.write(
            b"Aura bot is alive!"
        )

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(os.environ.get("PORT", 10000))

    while True:
        try:
            server = ThreadingHTTPServer(
                ("0.0.0.0", port),
                Handler
            )

            print(f"Web server запущен на порту {port}")

            server.serve_forever()

        except Exception as e:
            print(f"[WEB SERVER ERROR] {e}")
            print("Перезапуск web-сервера через 5 секунд...")
            time.sleep(5)


# =========================
# BOT START
# =========================

def start_bot():
    """
    Запускает polling и автоматически перезапускает его
    при временных ошибках сети / Telegram API.
    """

    while True:
        try:
            print("Запускаю Telegram polling...")

            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                skip_pending=True
            )

        except Exception as e:
            print("=" * 50)
            print("[BOT ERROR]")
            print(repr(e))
            print("Telegram polling упал.")
            print("Перезапуск через 5 секунд...")
            print("=" * 50)

            time.sleep(5)


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    print("Инициализация базы данных...")
    init_db()

    print("Запуск web-сервера...")
    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    print("Aura bot запускается...")

    start_bot()
