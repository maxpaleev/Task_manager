import random
import string

from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from datetime import datetime
from DB.database import SessionLocal
from DB.models import User, Event

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

@router.message(Command("events"))
async def events(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer('Ошибка - не передано число. Как должна выглядеть комманда:\n/events 27.12.2025 (число, месяц, год)')
        return
    try:
        date = datetime.strptime(command.args, '%d.%m.%Y')
    except ValueError:
        await message.answer('Ошибка - не верный формат даты. Как должна выглядеть комманда:\n/events 27.12.2025 (число, месяц, год)')
        return
    db = get_db()
    telegram_id = str(message.from_user.id)
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    abc = db.query(Event).filter(Event.user_id == user.id, Event.start_date == date).all()
    ev = []
    for i in abc:
        ev.append(f'Событие: {i.event_name}\nДата и время начала: {datetime.combine(i.start_date, i.time_start).strftime("%Y-%m-%d %H:%M")}\nДата и время конца: {datetime.combine(i.end_date, i.time_end).strftime("%Y-%m-%d %H:%M")}')
    await message.answer(f'События на {date.strftime("%Y-%m-%d")}:\n{"\n".join([i for i in ev])}')
    print(ev)