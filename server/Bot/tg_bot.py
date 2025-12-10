import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters.command import Command

BOT_TOKEN = "5921569584:AAEKfppjMRD1XEa80skgufMaZKEwS9iQKRU"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

database = sqlite3.connect("settings.db")
cursor = database.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    tg_id INTEGER
    )''')
database.commit()
database.close()


@dp.message(Command("start"))
async def start(message):
    tg_id = message.from_user.id
    print(type(tg_id))
    await message.answer("Hello, world! ID: " + str(tg_id))
    db = sqlite3.connect("settings.db")
    cur = db.cursor()
    cur.execute('''INSERT INTO users (tg_id) VALUES (?)''', (tg_id,))
    db.commit()
    db.close()

@dp.message(Command("id"))
async def cmd_id(message):
    db = sqlite3.connect("settings.db")
    cur = db.cursor()
    tg_id = cur.execute("SELECT tg_id FROM users WHERE tg_id = ?", (message.from_user.id, )).fetchone()[0]
    db.close()
    await message.answer(str(tg_id))

async def send_message(tg_id, text):
    await bot.send_message(tg_id, text)

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
