import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from DB.database import engine, Base, SessionLocal
from DB.models import User, Event
from .api import router as api_router
from ..Bot.tg_bot import BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOK = '5921569584:AAEKfppjMRD1XEa80skgufMaZKEwS9iQKRU'
INTERVAL = 60

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
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
            logger.info('No events to send')
            return

        logger.info(f'Found {len(events_to_send)} events to send')

        for event in events_to_send:
            user = db.query(User).filter(User.id == Event.user_id).first()

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
                logger.warning(f"User {user.id} not found or has no telegram_id")
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
    logger.info('Bot started')

    scheduler.add_job(check_events, 'interval', seconds=INTERVAL, id='check_events')
    scheduler.start()
    logger.info('Scheduler started')


@app.on_event('shutdown')
async def shutdown():
    logger.info("Остановка FastAPI...")
    scheduler.shutdown()
    logger.info("Планировщик APScheduler остановлен.")


app.include_router(api_router)
