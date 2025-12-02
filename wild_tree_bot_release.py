import asyncio
import logging
import os
import time
from pathlib import Path
from math import ceil

import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv

# --------------------------------------
# Load token
# --------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in .env")

# --------------------------------------
# Base settings
# --------------------------------------
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

ASSETS_DIR = Path("assets")
ASSETS_DIR.mkdir(exist_ok=True)
DB_PATH = Path("wildtree.db")

WATER_COOLDOWN = 300  # 5 minutes
DAILY_COOLDOWN = 24 * 3600
SUN_COOLDOWN = 600  # 10 minutes
MAX_LEVEL = 20

# --------------------------------------
# Database
# --------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                created REAL,
                last_water REAL,
                last_daily REAL,
                level INTEGER,
                exp INTEGER,
                sun INTEGER,
                water INTEGER
            )
            """
        )
        await db.commit()

async def ensure_user(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, time.time(), 0.0, 0.0, 1, 0, 0, 0),
            )
            await db.commit()

async def get_user(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, created, last_water, last_daily, level, exp, sun, water FROM users WHERE user_id=?",
            (uid,),
        )
        return await cur.fetchone()

async def update_user(uid: int, **kwargs):
    if not kwargs:
        return
    parts = ", ".join([f"{k}=?" for k in kwargs.keys()])
    values = list(kwargs.values())
    values.append(uid)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {parts} WHERE user_id=?", values)
        await db.commit()

# --------------------------------------
# Leveling
# --------------------------------------

def exp_needed_for(level: int) -> int:
    return ceil(5 * (level ** 1.6))

# --------------------------------------
# ASCII Art
# --------------------------------------
ASCII_TREE = {
    1: "🌱",
    2: "🌿",
    3: "🌳",
    4: "🌲",
    5: "🌴",
}

def ascii_for(level: int) -> str:
    if level < 3:
        return "  " + ASCII_TREE.get(level, "🌱") + "  "

    art = (
        "   " + ASCII_TREE.get(min(level, 5), "🌳") + "\n"
        "   /\\\n"
        "  //\\\\\\n"
        " ||  ||\n"
    )
    return art

# --------------------------------------
# Keyboards
# --------------------------------------

def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🌱 Посадить / Статус")
    kb.add("💧 Полить", "🌞 Дать солнце")
    kb.add("📜 Roadmap")
    kb.add("💰 Staking (скоро)")
    kb.add("🎁 Ежедневный бонус")
    kb.add("👤 Профиль")
    return kb

# --------------------------------------
# Handlers
# --------------------------------------

@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message):
    await init_db()
    await ensure_user(m.from_user.id)
    await m.answer("Добро пожаловать в Wild Tree!", reply_markup=main_keyboard())


# 🌱 СТАТУС (БЕЗ EXP)
@dp.message_handler(lambda m: m.text == "🌱 Посадить / Статус")
async def handler_status(m: types.Message):
    await ensure_user(m.from_user.id)
    u = await get_user(m.from_user.id)
    uid, created, last_water, last_daily, level, exp, sun, water = u

    needed = exp_needed_for(level)
    art = ascii_for(level)

    text = (
        f"🌱 Статус дерева\n\n"
        f"Уровень: {level}/{MAX_LEVEL}\n"
        f"EXP: {exp}/{needed}\n"
        f"Sun: {sun} ☀️\n"
        f"Water: {water} 💧\n\n"
        f"{art}"
    )

    await m.answer(text)


# 💧 Полить
@dp.message_handler(lambda m: m.text == "💧 Полить")
async def handler_water(m: types.Message):
    await ensure_user(m.from_user.id)
    u = await get_user(m.from_user.id)
    uid, created, last_water, last_daily, level, exp, sun, water = u
    now = time.time()

    # Проверка кулдауна
    if now - (last_water or 0) < WATER_COOLDOWN:
        remain = int(WATER_COOLDOWN - (now - last_water))
        mins = remain // 60
        secs = remain % 60
        return await m.answer(
            f"💧 Поливать можно раз в 5 минут!\n"
            f"Подожди {mins} мин {secs} сек."
        )

    # Успешный полив
    water += 1
    exp += 2
    await update_user(uid, water=water, exp=exp, last_water=now)

    await m.answer(f"💧 Полив! Water +1, EXP +2")
    await check_level_up(m, uid)


# 🌞 Солнце
@dp.message_handler(lambda m: m.text == "🌞 Дать солнце")
async def handler_sun(m: types.Message):
    await ensure_user(m.from_user.id)
    u = await get_user(m.from_user.id)
    uid, created, last_water, last_daily, level, exp, sun, water = u
    now = time.time()

    last_sun = getattr(handler_sun, "last_sun", 0)
    if now - last_sun < SUN_COOLDOWN:
        remain = int(SUN_COOLDOWN - (now - last_sun))
        mins = remain // 60
        secs = remain % 60
        return await m.answer(f"☀️ Солнце можно давать раз в 10 минут!\nПодожди {mins} мин {secs} сек.")

    handler_sun.last_sun = now

    sun += 1
    exp += 2
    await update_user(uid, sun=sun, exp=exp)

    await m.answer(f"☀️ Солнце! Sun +1, EXP +2")
    await check_level_up(m, uid)


# 🎉 Levelup
async def check_level_up(m: types.Message, uid: int):
    u = await get_user(uid)
    uid, created, last_water, last_daily, level, exp, sun, water = u

    while level < MAX_LEVEL and exp >= exp_needed_for(level):
        exp -= exp_needed_for(level)
        level += 1
        sun += 1
        water += 1
        await m.answer(f"🎉 Новый уровень: {level}! Sun+1, Water+1")

    await update_user(uid, level=level, exp=exp, sun=sun, water=water)


# 📜 Roadmap
@dp.message_handler(lambda m: m.text == "📜 Roadmap")
async def handler_roadmap(m: types.Message):
    await m.answer(
        "🗺️ Roadmap:\n"
        "1) Запуск токена\n"
        "2) Экономика и бот\n"
        "3) NFT + мета-лес\n"
        "4) W-Leaf экономика\n"
        "5) Метавселенная Forest"
    )


# 💰 Staking
@dp.message_handler(lambda m: m.text == "💰 Staking (скоро)")
async def handler_staking(m: types.Message):
    await m.answer("💰 Staking будет добавлен позже!")


# 🎁 Daily bonus
@dp.message_handler(lambda m: m.text == "🎁 Ежедневный бонус")
async def handler_daily(m: types.Message):
    await ensure_user(m.from_user.id)
    u = await get_user(m.from_user.id)
    uid, created, last_water, last_daily, level, exp, sun, water = u
    now = time.time()

    if now - (last_daily or 0) < DAILY_COOLDOWN:
        remain = int((last_daily + DAILY_COOLDOWN) - now)
        hrs = remain // 3600
        mins = (remain % 3600) // 60
        return await m.answer(f"Следующий бонус через {hrs}ч {mins}м")

    reward_sun = 1 + level // 5
    reward_water = 1 + level // 6
    reward_exp = 5 + level

    sun += reward_sun
    water += reward_water
    exp += reward_exp

    await update_user(uid, sun=sun, water=water, exp=exp, last_daily=now)

    await m.answer(
        f"🎁 Ежедневный бонус!\nSun+{reward_sun}, Water+{reward_water}, EXP+{reward_exp}"
    )
    await check_level_up(m, uid)


# 👤 Profile
@dp.message_handler(lambda m: m.text == "👤 Профиль")
async def handler_profile(m: types.Message):
    await ensure_user(m.from_user.id)
    u = await get_user(m.from_user.id)
    uid, created, last_water, last_daily, level, exp, sun, water = u
    needed = exp_needed_for(level)

    await m.answer(
        f"👤 Профиль: {m.from_user.first_name}\n"
        f"Уровень: {level}/{MAX_LEVEL}\n"
        f"EXP: {exp}/{needed}\n"
        f"Sun: {sun}☀️\n"
        f"Water: {water}💧"
    )


# fallback
@dp.message_handler()
async def fallback(m: types.Message):
    await m.answer("Используй кнопки меню!")

# --------------------------------------
# Start
# --------------------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    executor.start_polling(dp, skip_updates=True)
