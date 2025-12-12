import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters.command import Command

BOT_TOKEN = "5921569584:AAEKfppjMRD1XEa80skgufMaZKEwS9iQKRU"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()



@dp.message(Command("start"))
async def start(message):
    tg_id = message.from_user.id
    print(type(tg_id))
    await message.answer("Hello, world! ID: " + str(tg_id))


async def send_message(tg_id, text):
    await bot.send_message(tg_id, text)

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
