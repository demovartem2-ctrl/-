import os
import random
import asyncio
import ssl
import logging
from datetime import datetime, timezone

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
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

# --- ЛОГИКА НАГРАД (ТОЛЬКО 3) ---
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

# --- ТЕКСТ В ЛС (КАК НА СКРИНЕ, НО С ТВОИМИ УСЛОВИЯМИ) ---
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
        # Отправляем текст без кнопок, как ты просил
        await message.answer(ABOUT_TEXT, parse_mode="Markdown")
    else:
        # Если добавили в группу — короткое приветствие
        await message.answer("Я работаю в группах. Добавьте меня администратором, и я начну выдавать призы за активность!")

async def group_worker(bot: Bot, supabase: Client):
    while True:
        # Кулдаун 1-2 часа (3600-7200 секунд)
        wait_time = random.randint(3600, 7200)
        logging.info(f"Следующий розыгрыш через {wait_time // 60} минут.")
        await asyncio.sleep(wait_time)

        try:
            res = supabase.table("groups").select("chat_id").execute()
            if not res.data:
                continue

            for group in res.data:
                chat_id = group["chat_id"]
                users_res = supabase.table("users").select("username, user_id").limit(10).execute()
                if not users_res.data:
                    continue
                
                winner = random.choice(users_res.data)
                username = winner.get("username", "Unknown")
                user_id = winner["user_id"]

                reward = win_reward()
                now = datetime.now(timezone.utc).isoformat()

                supabase.table("users").upsert({
                    "user_id": user_id,
                    "username": username,
                    "last_win": now,
                    "total_wins": 1
                }).execute()

                text = (
                    f"🏆 **Победитель:** @{username}\n"
                    f"🎁 **Награда:** {reward['msg']}\n\n"
                    f"Напиши {ADMIN_USERNAME} для выдачи."
                )
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

        except Exception as e:
            logging.error(f"Ошибка в воркере: {e}")

# --- ЗАПУСК ---
async def main():
    api_server = TelegramAPIServer.from_base(API_BASE_URL)
    session = CustomAiohttpSession(api=api_server)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    dp.message.register(cmd_start, CommandStart())
    asyncio.create_task(group_worker(bot, supabase))

    logging.info("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
