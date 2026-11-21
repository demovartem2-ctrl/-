import os
import random
import time
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# --- Инициализация ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Константы ---
COOLDOWN_MIN = 3600  # 1 час в секундах
COOLDOWN_MAX = 7200  # 2 часа в секундах
ADMIN_USERNAME = "@sardelka"

REWARDS = [
    {"name": "1 NFT", "chance": 35, "message": "1 NFT"},
    {"name": "100 Stars", "chance": 50, "message": "100 Stars"},
    {"name": "5 NFT", "chance": 15, "message": "5 NFT"},
]

# --- Вспомогательные функции ---
def get_cooldown(user_id):
    # Получаем время последнего пульса
    res = supabase.table("users").select("last_pulse").eq("user_id", user_id).execute()
    if not res.data:
        return 0
    last = res.data[0]["last_pulse"]
    if last is None:
        return 0
    last_dt = datetime.fromisoformat(last)
    now = datetime.now(timezone.utc)
    elapsed = (now - last_dt).total_seconds()
    # Случайный кулдаун от 1 до 2 часов
    cooldown = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
    return max(0, cooldown - elapsed)

def win_reward():
    # Взвешенный случайный выбор
    roll = random.random() * 100
    cumulative = 0
    for reward in REWARDS:
        cumulative += reward["chance"]
        if roll <= cumulative:
            return reward
    return REWARDS[-1]

# --- Команда /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    text = (
        "Привет! Я бот для выдачи наград за активность.\n"
        "Используй /pulse, чтобы попытать удачу.\n"
        "Кулдаун: от 1 до 2 часов."
    )
    await message.answer(text)

# --- Команда /pulse ---
@dp.message(Command("pulse"))
async def cmd_pulse(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"

    # 1. Проверка кулдауна
    cooldown_left = get_cooldown(user_id)
    if cooldown_left > 0:
        minutes = int(cooldown_left // 60)
        await message.answer(f"⏳ Подожди ещё {minutes} минут(ы) перед следующей попыткой.")
        return

    # 2. Определение награды
    reward = win_reward()
    now = datetime.now(timezone.utc).isoformat()

    # 3. Обновление или вставка в БД
    data = supabase.table("users").upsert({
        "user_id": user_id,
        "username": username,
        "last_pulse": now,
        "total_wins": 1
    }).execute()

    # 4. Формирование сообщения
    await message.answer(
        f"🎉 Ты выбил награду: {reward['message']}!\n\n"
        f"Напиши {ADMIN_USERNAME} для её выдачи."
    )

# --- Webhook для Render ---
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

async def on_startup(app: web.Application):
    # Устанавливаем webhook при старте
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook")

def main():
    app = web.Application()
    # Путь для webhook
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    # Render передает порт через переменную PORT
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
