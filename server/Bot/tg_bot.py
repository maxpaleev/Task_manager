import random
import string

from aiogram import Router, types
from aiogram.filters import Command

from DB.database import SessionLocal
from DB.models import User

router = Router()


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def generate_random_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


@router.message(Command("start", "link"))
async def start(message: types.Message):
    if not message.from_user:
        return

    db = get_db()
    telegram_id = str(message.from_user.id)

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    link_code = generate_random_code()

    if user:
        if user.api_token:
            await message.answer("Ваше устройство уже связано! Генерирую новый код для перепривязки.")

        user.link_code = link_code
        db.commit()

    else:
        new_user = User(
            telegram_id=telegram_id,
            link_code=link_code
        )
        db.add(new_user)
        db.commit()

    response_text = (
        "🔗 **Связывание устройства**\n\n"
        "1. Откройте настройки Telegram в вашей программе на ПК.\n"
        "2. Введите этот уникальный код:\n\n"
        f"**`{link_code}`**\n\n"
        "Код действителен 15 минут."
    )
    await message.answer(response_text, parse_mode="Markdown")