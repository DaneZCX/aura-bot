"""
Модуль с командами /farm_aura и /rating для Telegram-бота на aiogram 3.

Как подключить:
    from aiogram import Dispatcher
    from aura_bot import router as aura_router

    dp.include_router(aura_router)

Не забудь один раз вызвать init_db() при старте бота (см. пример в конце файла).
"""

import random
import sqlite3
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

DB_PATH = "aura.db"

# Московское время (GMT+3), без привязки к DST — просто фиксированный оффсет
MSK = timezone(timedelta(hours=3))


# ---------- Работа с БД ----------

def init_db() -> None:
    """Создаёт таблицу, если её ещё нет. Вызвать один раз при старте бота."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aura_users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            aura INTEGER NOT NULL DEFAULT 0,
            last_farm_date TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
        """
    )
    conn.commit()
    conn.close()


def _get_msk_today_str() -> str:
    """Текущая дата по МСК в виде 'YYYY-MM-DD' — используется как ключ 'раз в день'."""
    return datetime.now(MSK).strftime("%Y-%m-%d")


def _upsert_user(chat_id: int, user_id: int, username: str | None, full_name: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO aura_users (chat_id, user_id, username, full_name, aura, last_farm_date)
        VALUES (?, ?, ?, ?, 0, NULL)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
        """,
        (chat_id, user_id, username, full_name),
    )
    conn.commit()
    conn.close()


def _get_last_farm_date(chat_id: int, user_id: int) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT last_farm_date FROM aura_users WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _apply_farm(chat_id: int, user_id: int, amount: int, today: str) -> int:
    """Прибавляет amount к ауре, обновляет дату фарма, возвращает итоговую ауру."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE aura_users
        SET aura = aura + ?, last_farm_date = ?
        WHERE chat_id = ? AND user_id = ?
        """,
        (amount, today, chat_id, user_id),
    )
    new_aura = conn.execute(
        "SELECT aura FROM aura_users WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ).fetchone()[0]
    conn.commit()
    conn.close()
    return new_aura


def _get_rating(chat_id: int, limit: int = 10) -> list[tuple[str, int]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT COALESCE(full_name, username, 'Без имени') AS name, aura
        FROM aura_users
        WHERE chat_id = ?
        ORDER BY aura DESC
        LIMIT ?
        """,
        (chat_id, limit),
    ).fetchall()
    conn.close()
    return rows


# ---------- Хендлеры ----------

def _display_name(message: Message) -> str:
    user = message.from_user
    return user.full_name or (f"@{user.username}" if user.username else str(user.id))


@router.message(Command("farm_aura"))
async def cmd_farm_aura(message: Message) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = _display_name(message)

    _upsert_user(chat_id, user_id, username, full_name)

    today = _get_msk_today_str()
    last_date = _get_last_farm_date(chat_id, user_id)

    if last_date == today:
        # Считаем время до следующей полуночи по МСК
        now_msk = datetime.now(MSK)
        tomorrow_msk = (now_msk + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        left = tomorrow_msk - now_msk
        hours, rem = divmod(int(left.total_seconds()), 3600)
        minutes = rem // 60

        await message.reply(
            f"⏳ Ты уже фармил ауру сегодня!\n"
            f"Приходи через {hours} ч {minutes} мин"
        )
        return

    amount = random.randint(-5, 15)
    new_aura = _apply_farm(chat_id, user_id, amount, today)

    if amount > 10:
        emoji, comment = "🔥😎", "Невероятный день, аура прёт!"
    elif amount > 0:
        emoji, comment = "✨🙂", "Небольшой, но приятный плюсик."
    elif amount == 0:
        emoji, comment = "😐", "Ни туда ни сюда."
    else:
        emoji, comment = "💀📉", "Ой, сегодня не твой день..."

    sign = "+" if amount >= 0 else ""
    await message.reply(
        f"{emoji} {full_name}, ты получил(а) {sign}{amount} ауры!\n"
        f"{comment}\n"
        f"💫 Твоя аура сейчас: {new_aura}"
    )


@router.message(Command("rating"))
async def cmd_rating(message: Message) -> None:
    chat_id = message.chat.id
    rows = _get_rating(chat_id, limit=10)

    if not rows:
        await message.reply(
            "Рейтинг пока пуст 😶 Используйте /farm_aura, чтобы начать фармить ауру!"
        )
        return

    place_emojis = ["🥇", "🥈", "🥉"]
    lines = ["📊 <b>Рейтинг ауры</b>\n"]

    for i, (name, aura) in enumerate(rows):
        if i == 0:
            lines.append(
                f"{place_emojis[0]} <b>{name}</b> — {aura} 💥\n"
                f"    😤🔥 Он моггает всех!"
            )
        elif i < len(place_emojis):
            lines.append(f"{place_emojis[i]} {name} — {aura}")
        else:
            lines.append(f"{i + 1}. {name} — {aura}")

    await message.reply("\n".join(lines), parse_mode="HTML")


# ---------- Пример запуска (если хочешь протестировать файл отдельно) ----------
if __name__ == "__main__":
    import asyncio
    import os
    from aiogram import Bot, Dispatcher

    async def main():
        init_db()
        # Токен берётся из переменной окружения BOT_TOKEN.
        # Локально можно положить его в файл .env (и добавить .env в .gitignore),
        # на Render — задать через Dashboard -> Environment -> BOT_TOKEN.
        bot = Bot(token=os.environ["BOT_TOKEN"])
        dp = Dispatcher()
        dp.include_router(router)
        await dp.start_polling(bot)

    asyncio.run(main())
