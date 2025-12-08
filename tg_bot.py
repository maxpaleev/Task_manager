import asyncio
import threading
import sqlite3
import datetime
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

# ==========================================
# КОНФИГУРАЦИЯ И СВЯЗЬ
# ==========================================

# Глобальные переменные для связи между потоками
bot_instance: Optional[Bot] = None  # Объект бота
bot_loop: Optional[asyncio.AbstractEventLoop] = None  # Цикл событий (Event Loop) бота
CURRENT_CHAT_ID: Optional[int] = None  # ID пользователя для отправки уведомлений

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка команды /start: сохраняет Chat ID и обновляет глобальную переменную."""
    db = sqlite3.connect('settings.db')
    cur = db.cursor()
    # Сохраняем ID пользователя
    cur.execute('UPDATE settings SET telegram_id = ?', (message.chat.id,))
    db.commit()
    db.close()

    global CURRENT_CHAT_ID
    # Убеждаемся, что глобальная переменная обновлена
    CURRENT_CHAT_ID = message.chat.id

    await message.answer(f"Привет! Я запомнил этот чат (ID: {CURRENT_CHAT_ID}).\n"
                         f"Теперь сюда будут приходить уведомления из планировщика.")


# ==========================================
# ФУНКЦИИ ЗАПУСКА И ОТПРАВКИ
# ==========================================
async def start_bot():
    """Асинхронная функция запуска, загружает токен и chat_id."""
    global bot_instance, CURRENT_CHAT_ID
    db = sqlite3.connect('settings.db')
    cur = db.cursor()

    # Загрузка токена и telegram_id
    settings_row = cur.execute('SELECT bot_token, telegram_id FROM settings').fetchone()
    db.close()

    if not settings_row or not settings_row[0]:
        # Токен не найден или пуст (бот не будет запущен)
        return

    API_TOKEN = settings_row[0]
    chat_id_from_db = settings_row[1]

    # Проверяем на None, чтобы избежать ошибки int(None)
    CURRENT_CHAT_ID = int(chat_id_from_db) if chat_id_from_db is not None else None

    bot_instance = Bot(token=API_TOKEN)
    await dp.start_polling(bot_instance)


def run_bot_thread():
    """Запускает бота в отдельном синхронном потоке."""
    global bot_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_loop = loop
    # Запуск асинхронной функции в этом потоке
    loop.run_until_complete(start_bot())


def send_notification(name: str, time_s: datetime.time, time_e: datetime.time) -> bool:
    """
    Основная функция для отправки уведомлений из GUI-потока в Telegram.
    Использует run_coroutine_threadsafe для безопасной связи.
    """
    global bot_instance, bot_loop, CURRENT_CHAT_ID

    # Проверяем готовность: объект бота, цикл и установленный (int) chat_id
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
            return False
    else:
        return False
