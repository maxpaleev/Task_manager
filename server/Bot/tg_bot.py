import random
import string

from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from datetime import datetime
from server.DB.database import SessionLocal
from server.DB.models import User, Event, Task

router = Router()


def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    telegram_id = str(message.from_user.id)
    link_code = generate_code()

    with SessionLocal() as db:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id)
            db.add(user)

        # Всегда обновляем код при запросе /start, если токена еще нет или нужна перепривязка
        user.link_code = link_code
        db.commit()

        text = (
            "🔗 **Связывание устройства**\n"
            "Введите этот код в приложении на ПК:\n\n"
            f"**`{link_code}`**"
        )
        await message.answer(text, parse_mode="Markdown")


@router.message(Command("events"))
async def cmd_events(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Используйте: /events ДД.ММ.ГГГГ")
        return

    try:
        query_date = datetime.strptime(command.args, '%d.%m.%Y').date()
    except ValueError:
        await message.answer("Неверный формат даты.")
        return

    with SessionLocal() as db:
        user = db.query(User).filter(User.telegram_id == str(message.from_user.id)).first()
        if not user:
            await message.answer("Вы не зарегистрированы.")
            return

        events = db.query(Event).filter(Event.user_id == user.id, Event.start_date == query_date).all()

        if not events:
            await message.answer(f"На {query_date} событий нет.")
            return

        response = [f"📅 **{query_date}**"]
        for e in events:
            if e.start_date == e.end_date:
                time_range = f"{e.time_start.strftime('%H:%M')} - {e.time_end.strftime('%H:%M')}"
                response.append(f"• {e.event_name} ({time_range})")
            else:
                response.append(
                    f"• {e.event_name} ({e.start_date.strftime('%d.%m.%Y')}{e.time_start.strftime(' %H:%M')} - {e.end_date.strftime('%d.%m.%Y')}{e.time_end.strftime(' %H:%M')})")

        await message.answer("\n".join(response), parse_mode="Markdown")


@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    with SessionLocal() as db:
        user = db.query(User).filter(User.telegram_id == str(message.from_user.id)).first()
        if not user:
            await message.answer("Вы не зарегистрированы.")
            return
        tasks = db.query(Task).filter(Task.user_id == user.id).all()
        if not tasks:
            await message.answer("У вас нет задач.")
            return
        response = [f"📝 **Ваши задачи**"]
        category = {}
        for task in tasks:
            if task.category in category:
                category[task.category].append((task.name, task.description))
            else:
                category[task.category] = [(task.name, task.description)]
        for cat in category:
            response.append(f"• {cat}")
            for task in category[cat]:
                if task[1]:
                    response.append(f"    ◦ {task[0]} ({task[1]})")
                else:
                    response.append(f"    ◦ {task[0]}")
        await message.answer("\n".join(response), parse_mode="Markdown")
