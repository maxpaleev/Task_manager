import logging
import random
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from aiogram import Bot, Dispatcher
from server.Bot.tg_bot import router as bot_router
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from DB.database import engine, Base, SessionLocal, get_db
from DB.models import User, Event
from .api import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOK = '5921569584:AAEKfppjMRD1XEa80skgufMaZKEwS9iQKRU'
INTERVAL = 60

app = FastAPI()
bot = Bot(token=BOT_TOK)
dp = Dispatcher()
scheduler = AsyncIOScheduler()


async def check_events():
    # Используем контекстный менеджер для сессии (гарантирует закрытие)
    with SessionLocal() as db:
        try:
            now_check = datetime.now()
            # Eager loading не нужен, так как мы берем простые поля, но сессия нужна чистая
            events_to_send = db.query(Event).filter(
                Event.start_time <= now_check,
                Event.is_sent == False
            ).all()

            if not events_to_send:
                return

            for event in events_to_send:
                # Оптимизация: можно использовать join, но для простоты оставим так
                user = db.query(User).filter(User.id == event.user_id).first()

                if user and user.telegram_id:
                    try:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=f"⏰ Напоминание: {event.text}"
                        )
                        event.is_sent = True
                    except Exception as e:
                        logger.error(f"TG Error: {e}")
                else:
                    # Если пользователя нет, помечаем как отправленное (или ошибочное),
                    # чтобы не спамить в лог каждую минуту
                    event.is_sent = True

            db.commit()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            db.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info('Starting up...')
    Base.metadata.create_all(bind=engine)

    scheduler.add_job(check_events, 'interval', seconds=60, id='check_events')
    scheduler.start()

    dp.include_router(bot_router)
    # Запускаем поллинг в фоне
    polling_task = asyncio.create_task(dp.start_polling(bot))

    yield  # Приложение работает здесь

    # --- Shutdown ---
    logger.info("Shutting down...")
    scheduler.shutdown()
    await bot.session.close()
    polling_task.cancel()  # Останавливаем поллинг
    try:
        await polling_task
    except asyncio.CancelledError:
        pass


# Инициализация приложения с lifespan
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)