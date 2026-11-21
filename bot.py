import os
import random
import asyncio
import ssl
from datetime import datetime, timezone

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.client.session.aiohttp import AiohttpSession
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "https://31.76.29.36:8081/bot")

# --- ЛОГИКА ---
COOLDOWN_MIN = 3600
COOLDOWN_MAX = 7200
ADMIN_USERNAME = "@sardelka"

REWARDS = [
    {"name": "1 NFT", "chance": 35, "message": "1 NFT"},
    {"name": "100 Stars", "chance": 50, "message": "100 Stars"},
    {"name": "5 NFT", "chance": 15, "message": "5 NFT"},
]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_cooldown(user_id):
    try:
        res = supabase.table("users").select("last_pulse").eq("user_id", user_id).execute()
        if not res.data or not res.data[0]["last_pulse"]:
            return 0
        last = res.data[0]["last_pulse"]
        last_dt = datetime.fromisoformat(last)
        now = datetime.now(timezone.utc)
        elapsed = (now - last_dt).total_seconds()
        cooldown = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        return max(0, cooldown - elapsed)
    except Exception as e:
        print(f"Ошибка БД: {e}")
        return 0

def win_reward():
    roll = random.random() * 100
    cumulative = 0
    for reward in REWARDS:
        cumulative += reward["chance"]
        if roll <= cumulative:
            return reward
    return REWARDS[-1]

async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для выдачи наград за активность.\nИспользуй /pulse, чтобы попытать удачу.\nКулдаун: от 1 до 2 часов.")

async def cmd_pulse(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"

    cooldown_left = get_cooldown(user_id)
    if cooldown_left > 0:
        minutes = int(cooldown_left // 60)
        await message.answer(f"⏳ Подожди ещё {minutes} минут(ы) перед следующей попыткой.")
        return

    reward = win_reward()
    now = datetime.now(timezone.utc).isoformat()

    try:
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": username,
            "last_pulse": now,
            "total_wins": 1
        }).execute()
    except Exception as e:
        print(f"Ошибка записи в БД: {e}")

    await message.answer(
        f"🎉 Ты выбил награду: {reward['message']}!\n\n"
        f"Напиши {ADMIN_USERNAME} для её выдачи."
    )

# --- ЗАПУСК ---
async def main():
    # 1. Создаем SSL-контекст и коннектор ВНУТРИ асинхронного loop
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    # 2. Создаем AiohttpSession
    session = AiohttpSession(api=API_BASE_URL)
    # 3. Подменяем internal _connector сессии на наш коннектор
    #    чтобы aiogram использовал именно его
    session._connector = connector

    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_pulse, Command("pulse"))

    print("Запуск бота...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
