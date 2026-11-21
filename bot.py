import os
import random
import asyncio
import ssl
import logging
from datetime import datetime, timezone, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from supabase import create_client, Client

# --- Отключаем спам в логах ---
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
API_BASE_URL = "https://31.76.29.36:8081"

# --- КАСТОМНАЯ СЕССИЯ (SSL) ---
class CustomAiohttpSession(AiohttpSession):
    async def create_session(self) -> aiohttp.ClientSession:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        return aiohttp.ClientSession(connector=connector)

# --- ЛОГИКА НАГРАД ---
REWARDS = [
    {"name": "1 NFT", "chance": 35, "msg": "1 NFT"},
    {"name": "100 Stars", "chance": 50, "msg": "100 Stars"},
    {"name": "5 NFT", "chance": 15, "msg": "5 NFT"},
]
ADMIN_USERNAME = "@sardelka"

def win_reward():
    roll = random.random() * 100
    cumulative = 0
    for reward in REWARDS:
        cumulative += reward["chance"]
        if roll <= cumulative:
            return reward
    return REWARDS[-1]

# --- ТЕКСТ В ЛС ---
ABOUT_TEXT = (
    "**Flashgram Pulse: один приз за активность.**\n"
    "Мишка, NFT или Stars. Нужны номер и привязанный аккаунт Flashgram.\n"
    "Добавьте бота администратором группы.\n\n"
    "🎰 35% · ⭐ 50% · 💎 15%\n"
    "Награды: 1 NFT (35%), 100 Stars (50%), 5 NFT (15%).\n\n"
    "Нужны выданный номер и аккаунт Flashgram. Основной аккаунт — тот, что привязан в боте регистрации."
)

# --- ФУНКЦИИ ---
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        await message.answer(ABOUT_TEXT, parse_mode="Markdown")
    else:
        await message.answer("Добавьте меня администратором, и я начну выдавать призы за активность! Пишите /pulse, чтобы испытать удачу.")

async def cmd_pulse(message: types.Message, bot: Bot, supabase: Client):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    # 1. Проверяем, есть ли пользователь в базе и когда последний раз пульсировал
    try:
        res = supabase.table("users").select("last_pulse").eq("user_id", user_id).execute()
        
        # Если запись есть, проверяем время
        if res.data and res.data[0].get("last_pulse"):
            last_pulse = datetime.fromisoformat(res.data[0]["last_pulse"])
            now = datetime.now(timezone.utc)
            elapsed = (now - last_pulse).total_seconds()
            
            # Кулдаун от 1 до 2 часов
            cooldown = random.randint(3600, 7200)
            
            if elapsed < cooldown:
                remaining = int((cooldown - elapsed) // 60)
                await message.reply(f"⏳ Подожди ещё {remaining} минут(ы) перед следующей попыткой.")
                return
    except Exception as e:
        logging.error(f"Ошибка БД при проверке: {e}")

    # 2. Разворачиваем награду
    reward = win_reward()
    now = datetime.now(timezone.utc).isoformat()

    # 3. Обновляем БД (записываем время пульса и победу)
    try:
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": username,
            "last_pulse": now,
            "total_wins": 1
        }).execute()
    except Exception as e:
        logging.error(f"Ошибка записи в БД: {e}")

    # 4. Отправляем ответ в чат (похожий на скрин)
    text = (
        f"🎰 **Flashgram Pulse**\n"
        f"🎰 35% · ⭐ 50% · 💎 15%\n"
        f"**Один приз активному участнику.**\n\n"
        f"🏆 Победитель: **@{username}**\n"
        f"🎁 Награда: **{reward['msg']}**\n\n"
        f"Напиши {ADMIN_USERNAME} для выдачи."
    )
    await message.reply(text, parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    api_server = TelegramAPIServer.from_base(API_BASE_URL)
    session = CustomAiohttpSession(api=api_server)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Регистрируем команды
    dp.message.register(cmd_start, CommandStart())
    # Передаем bot и supabase как аргументы в хендлер
    dp.message.register(cmd_pulse, Command("pulse"), bot=bot, supabase=supabase)

    logging.info("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
