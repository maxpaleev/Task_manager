import logging
import random
import asyncio
from datetime import datetime, timezone

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
    logger.info('Checking events...')

    db: Session = SessionLocal()

    try:
        now_check = datetime.now()

        events_to_send = db.query(Event).filter(
            Event.start_time <= now_check,
            Event.is_sent == False
        ).all()

        if not events_to_send:
            logger.info('НЕТ СОБЫТИЙ ДЛЯ ОТПРАВКИ')
            return

        logger.info(f'Found {len(events_to_send)} events to send')

        for event in events_to_send:
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Использование event.user_id
            user = db.query(User).filter(User.id == event.user_id).first()

            if user and user.telegram_id:
                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=f"⏰ Напоминание о событии ({event.start_time.strftime('%H:%M')}): {event.text}"
                    )
                    event.is_sent = True
                    db.add(event)
                except Exception as e:
                    logger.error(f"Error sending message to user {user.telegram_id}: {e}")
            else:
                user_id_log = user.id if user else event.user_id
                logger.warning(f"User {user_id_log} not found or has no telegram_id")
        db.commit()
    except Exception as e:
        logger.error(f"Error checking events: {e}")
        db.rollback()
    finally:
        db.close()


@app.on_event('startup')
async def startup():
    logger.info('Starting up...')
    Base.metadata.create_all(bind=engine)
    logger.info('Database tables checked')

    scheduler.add_job(check_events, 'interval', seconds=INTERVAL, id='check_events')
    scheduler.start()
    logger.info('Scheduler started')

    dp.include_router(bot_router)
    # Используем asyncio для запуска Polling в фоновом режиме
    asyncio.create_task(dp.start_polling(bot))
    logger.info('Bot polling started')


@app.on_event('shutdown')
async def shutdown():
    logger.info("Остановка FastAPI...")
    scheduler.shutdown()
    logger.info("Планировщик APScheduler остановлен.")


app.include_router(api_router)