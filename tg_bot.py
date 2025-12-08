import asyncio
import threading
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

# ==========================================
# КОНФИГУРАЦИЯ И СВЯЗЬ
# ==========================================

# Вставьте сюда токен, который дал @BotFather
API_TOKEN = '5921569584:AAEKfppjMRD1XEa80skgufMaZKEwS9iQKRU'

# Глобальные переменные для связи между потоками
bot_instance = None  # Объект бота
bot_loop = None  # Цикл событий (Event Loop) бота
CURRENT_CHAT_ID = None  # ID пользователя для отправки уведомлений

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    global CURRENT_CHAT_ID
    CURRENT_CHAT_ID = message.chat.id
    await message.answer(f"Привет! Я запомнил этот чат (ID: {CURRENT_CHAT_ID}).\n"
                         f"Теперь сюда будут приходить уведомления из планировщика.")


# ==========================================
# ФУНКЦИИ ЗАПУСКА И ОТПРАВКИ
# ==========================================
async def start_bot():
    global bot_instance
    bot_instance = Bot(token=API_TOKEN)
    await dp.start_polling(bot_instance)


def run_bot_thread():
    global bot_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_loop = loop
    loop.run_until_complete(start_bot())


def send_notification(name: str, time_s, time_e):
    """
    Основная функция для отправки уведомлений из GUI-потока в Telegram.
    Использует run_coroutine_threadsafe для безопасной связи.
    """
    global bot_instance, bot_loop, CURRENT_CHAT_ID

    if bot_instance and bot_loop and CURRENT_CHAT_ID:
        time_s_str = time_s.strftime("%H:%M")
        time_e_str = time_e.strftime("%H:%M")
        message_text = (f"⏰ <b>Напоминание о событии!</b>\n\n"
                        f"Время: {time_s_str} - {time_e_str}\n"
                        f"Событие: {name}")

        try:
            # Передаем асинхронную задачу в цикл событий бота
            asyncio.run_coroutine_threadsafe(
                bot_instance.send_message(CURRENT_CHAT_ID, message_text, parse_mode="HTML"),
                bot_loop
            )
            return True
        except Exception:
            # При ошибке возвращаем False, чтобы основной код мог показать предупреждение
            return False
    else:
        return False