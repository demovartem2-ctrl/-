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

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    "Бот выбирает победителя из активных участников раз в 1-2 часа."
)

# --- ФУНКЦИЯ СБОРА АКТИВНОСТИ ---
# Эта функция срабатывает на КАЖДОЕ сообщение в чате и сохраняет активных юзеров
async def track_activity(message: types.Message):
    if message.chat.type in ["group", "supergroup"]:
        user_id = message.from_user.id
        username = message.from_user.username or "Unknown"
        
        # Обновляем время последней активности в БД
        try:
            supabase.table("active_users").upsert({
                "user_id": user_id,
                "username": username,
                "chat_id": message.chat.id,
                "last_active": datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            logging.error(f"Ошибка трекинга: {e}")

# --- ФОНОВЫЙ ВОРКЕР (РАЗ В 1-2 ЧАСА) ---
async def hourly_worker(bot: Bot):
    while True:
        # Ждем случайное время от 1 до 2 часов (в секундах)
        wait_time = random.randint(3600, 7200)
        logging.info(f"Следующий розыгрыш через {wait_time // 60} минут.")
        await asyncio.sleep(wait_time)

        try:
            # Получаем список групп, где есть активность
            groups_res = supabase.table("active_users").select("chat_id").execute()
            if not groups_res.data:
                continue
            
            # Собираем уникальные chat_id
            chat_ids = list(set([g["chat_id"] for g in groups_res.data]))

            for chat_id in chat_ids:
                # Берем всех, кто был активен в этой группе за последние 2 часа
                time_threshold = (datetime.now(timezone.utc) - asyncio.timedelta(hours=2)).isoformat()
                users_res = supabase.table("active_users").select("username, user_id").eq("chat_id", chat_id).gte("last_active", time_threshold).execute()
                
                if not users_res.data:
                    continue
                
                # Выбираем случайного победителя
                winner = random.choice(users_res.data)
                username = winner.get("username", "Unknown")
                reward = win_reward()

                text = (
                    f"🎰 **Flashgram Pulse**\n"
                    f"🎰 35% · ⭐ 50% · 💎 15%\n"
                    f"**Один приз активному участнику.**\n\n"
                    f"🏆 Победитель: **@{username}**\n"
                    f"🎁 Награда: **{reward['msg']}**\n\n"
                    f"Напиши {ADMIN_USERNAME} для выдачи."
                )
                
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

                # Очищаем активность для этой группы, чтобы не спамить одними и теми же
                supabase.table("active_users").delete().eq("chat_id", chat_id).execute()

        except Exception as e:
            logging.error(f"Ошибка в воркере: {e}")

async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        await message.answer(ABOUT_TEXT, parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    api_server = TelegramAPIServer.from_base(API_BASE_URL)
    session = CustomAiohttpSession(api=api_server)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    # Регистрируем хендлеры
    dp.message.register(cmd_start, CommandStart())
    # Регистрируем трекер активности на все сообщения (без фильтра команд)
    dp.message.register(track_activity)

    # Запускаем фоновый воркер
    asyncio.create_task(hourly_worker(bot))

    logging.info("Бот запущен. Трекер активности и воркер работают.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
