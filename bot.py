import os
import random
import asyncio
import ssl
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import TCPConnector
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
# ВСТАВЬ СВОЙ ТОКЕН СЮДА ВРУЧНУЮ:
BOT_TOKEN = "354:3YibVbSxoEelu7cQZzeoaXRs4S44jAAXTg2"

# Твои ключи Supabase
SUPABASE_URL = "https://твой-проект.supabase.co"
SUPABASE_KEY = "твой_secret_ключ"

# Твой кастомный API сервер
API_BASE_URL = "https://31.76.29.36:8081/bot"

# --- ИНИЦИАЛИЗАЦИЯ ---
# Отключаем проверку SSL, если у сервера самоподписанный сертификат
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
connector = TCPConnector(ssl=ssl_context)

# Указываем aiogram использовать твой API
session = AiohttpSession(api=API_BASE_URL, connector=connector)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ЛОГИКА ---
COOLDOWN_MIN = 3600
COOLDOWN_MAX = 7200
ADMIN_USERNAME = "@sardelka"

REWARDS = [
    {"name": "1 NFT", "chance": 35, "message": "1 NFT"},
    {"name": "100 Stars", "chance": 50, "message": "100 Stars"},
    {"name": "5 NFT", "chance": 15, "message": "5 NFT"},
]

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

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для выдачи наград за активность.\nИспользуй /pulse, чтобы попытать удачу.\nКулдаун: от 1 до 2 часов.")

@dp.message(Command("pulse"))
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

# --- ЗАПУСК (POLLING) ---
async def main():
    print("Запуск бота в режиме Polling...")
    # Удаляем вебхук, чтобы бот не пытался стучаться на старый адрес
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 
