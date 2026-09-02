import os
import random
import sqlite3
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import telebot


# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("❌ Переменная BOT_TOKEN не найдена!")

DB_FILE = os.environ.get("DB_FILE", "aura.db")

bot = telebot.TeleBot(TOKEN)


# ============================================================
# DATABASE
# ============================================================

def get_db():
    """
    Создаём отдельное соединение с SQLite для каждого запроса.
    WAL + busy_timeout помогают избежать проблем при
    одновременном обращении нескольких потоков.
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

        print("✅ База данных готова.")

    except sqlite3.Error as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        raise

    finally:
        db.close()


# ============================================================
# ДОБАВЛЕНИЕ / ПОЛУЧЕНИЕ ПОЛЬЗОВАТЕЛЯ
# ============================================================

def get_or_create_user(user_id, name):
    """
    Возвращает:
        aura, last_farm
    """

    db = get_db()

    try:
        user = db.execute(
            """
            SELECT aura, last_farm
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        if user is None:
            db.execute(
                """
                INSERT INTO users (
                    user_id,
                    name,
                    aura,
                    last_farm
                )
                VALUES (?, ?, ?, ?)
                """,
                (user_id, name, 0, None)
            )

            db.commit()

            return 0, None

        aura, last_farm = user

        # Обновляем имя на актуальное
        db.execute(
            """
            UPDATE users
            SET name = ?
            WHERE user_id = ?
            """,
            (name, user_id)
        )

        db.commit()

        return aura, last_farm

    finally:
        db.close()


# ============================================================
# /farm_aura
# ============================================================

@bot.message_handler(commands=["farm_aura"])
def farm_aura(message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "Игрок"

    today = date.today().isoformat()

    try:
        aura, last_farm = get_or_create_user(
            user_id,
            name
        )

    except sqlite3.Error as e:
        print(f"[DB ERROR] get_or_create_user: {e}")

        try:
            bot.reply_to(
                message,
                "⚠️ Ошибка базы данных. Попробуй ещё раз."
            )
        except Exception as reply_error:
            print(f"[TELEGRAM ERROR] {reply_error}")

        return

    # Уже фармил сегодня
    if last_farm == today:
        try:
            bot.reply_to(
                message,
                "💀 Ты уже фармил ауру сегодня!\n"
                "Приходи завтра."
            )
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

        return

    # От -3 до +10
    gained = random.randint(-3, 10)

    new_aura = aura + gained

    db = get_db()

    try:
        db.execute(
            """
            UPDATE users
            SET
                name = ?,
                aura = ?,
                last_farm = ?
            WHERE user_id = ?
            """,
            (
                name,
                new_aura,
                today,
                user_id
            )
        )

        db.commit()

    except sqlite3.Error as e:
        print(f"[DB ERROR] farm update: {e}")

        try:
            bot.reply_to(
                message,
                "⚠️ Не удалось сохранить ауру. "
                "Попробуй ещё раз."
            )
        except Exception as reply_error:
            print(f"[TELEGRAM ERROR] {reply_error}")

        return

    finally:
        db.close()

    # Текст результата
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
        print(f"[TELEGRAM ERROR] farm reply: {e}")


# ============================================================
# /rating
# ============================================================

@bot.message_handler(commands=["rating"])
def rating(message):
    db = get_db()

    try:
        users = db.execute(
            """
            SELECT user_id, name, aura
            FROM users
            ORDER BY aura DESC, user_id ASC
            LIMIT 10
            """
        ).fetchall()

        # Для диагностики
        total_users = db.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        print(
            f"[RATING] Всего пользователей в БД: {total_users}"
        )

        print(
            f"[RATING] В топ-10: {len(users)}"
        )

        print(
            f"[RATING] Данные: {users}"
        )

    except sqlite3.Error as e:
        print(f"[DB ERROR] rating: {e}")

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
        try:
            bot.reply_to(
                message,
                "🏆 Рейтинг пока пуст!"
            )
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

        return

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    lines = [
        "🏆 РЕЙТИНГ АУРЫ",
        ""
    ]

    for i, (user_id, name, aura) in enumerate(
        users,
        start=1
    ):

        if i <= 3:
            prefix = medals[i - 1]
        else:
            prefix = f"{i}."

        # Защита от пустого имени
        if not name:
            name = "Игрок"

        lines.append(
            f"{prefix} {name} — {aura} ауры"
        )

        if i == 1:
            lines.append(
                "   💀 ОН МОГГАЕТ ВСЕХ!"
            )

    text = "\n".join(lines)

    print(
        f"[RATING] Отправляю сообщение:\n{text}"
    )

    try:
        bot.reply_to(
            message,
            text
        )

    except Exception as e:
        print(
            f"[TELEGRAM ERROR] rating reply: {e}"
        )


# ============================================================
# WEB SERVER
# ============================================================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )

            self.end_headers()

            self.wfile.write(
                b"Aura bot is alive!"
            )

        except Exception as e:
            print(
                f"[WEB ERROR] GET: {e}"
            )

    def do_HEAD(self):
        try:
            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )

            self.end_headers()

        except Exception as e:
            print(
                f"[WEB ERROR] HEAD: {e}"
            )

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    while True:

        try:
            server = ThreadingHTTPServer(
                (
                    "0.0.0.0",
                    port
                ),
                Handler
            )

            print(
                f"🌐 Web server запущен "
                f"на порту {port}"
            )

            server.serve_forever()

        except Exception as e:

            print(
                f"[WEB SERVER ERROR] {repr(e)}"
            )

            print(
                "🔄 Перезапуск web-сервера "
                "через 5 секунд..."
            )

            time.sleep(5)


# ============================================================
# TELEGRAM POLLING
# ============================================================

def start_bot():

    while True:

        try:

            print(
                "🤖 Запускаю Telegram polling..."
            )

            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                skip_pending=True
            )

            print(
                "⚠️ Polling завершился."
            )

        except Exception as e:

            print("=" * 60)
            print("❌ TELEGRAM BOT ERROR")
            print("=" * 60)

            print(
                repr(e)
            )

            print("=" * 60)

            print(
                "🔄 Перезапуск Telegram polling "
                "через 5 секунд..."
            )

            time.sleep(5)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("✨ AURA BOT")
    print("=" * 60)

    # База
    print("📦 Инициализация базы данных...")
    init_db()

    # Web server
    print("🌐 Запуск web-сервера...")

    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True
    )

    web_thread.start()

    # Telegram
    print("🤖 Запуск Telegram бота...")

    start_bot()
