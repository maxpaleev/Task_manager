import random
import string

from aiogram import Router, types
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from server.DB.database import SessionLocal
from server.DB.models import User, Event, Task

router = Router()


class CreateEvent(StatesGroup):
    name = State()
    start = State()
    end = State()
    chose = State()


class CreateTask(StatesGroup):
    name = State()
    description = State()
    category = State()
    check = State()


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


# -------------------------------------------------------------------
# Логика событий
# -------------------------------------------------------------------


@router.message(Command("events"))
async def cmd_events(message: types.Message, command: CommandObject):
    with SessionLocal() as db:
        user = db.query(User).filter(User.telegram_id == str(message.from_user.id)).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы.")
            return

        if not command.args:
            dates = db.query(Event.start_date).distinct().filter(Event.user_id == user.id).all()
            if dates:
                date_list = "\n".join([f"🔹 {date[0].strftime('%d.%m.%Y')}" for date in dates])
                await message.answer(
                    text="Чтобы вывести события на дату, введите команду:\n"
                         "`/events ДД.ММ.ГГГГ` \n\n"
                         f"📅 **Доступные даты:**\n{date_list}",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(text="📭 Доступных дат нет.")
            return

        try:
            query_date = datetime.strptime(command.args, '%d.%m.%Y').date()
        except ValueError:
            await message.answer("⚠️ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return

        events = db.query(Event).filter(Event.user_id == user.id, Event.start_date == query_date).all()

        if not events:
            await message.answer(f"На {query_date.strftime('%d.%m.%Y')} событий нет.")
            return

        response = [f"📅 **События на {query_date.strftime('%d.%m.%Y')}**\n"]
        for e in events:
            # Выбираем иконку в зависимости от статуса
            status_icon = "✅" if e.is_completed else "⏳"

            if e.start_date == e.end_date:
                time_range = f"{e.time_start.strftime('%H:%M')} - {e.time_end.strftime('%H:%M')}"
                response.append(f"{status_icon} **{e.event_name}** ({time_range})")
            else:
                start_dt = f"{e.start_date.strftime('%d.%m')} {e.time_start.strftime('%H:%M')}"
                end_dt = f"{e.end_date.strftime('%d.%m')} {e.time_end.strftime('%H:%M')}"
                response.append(f"{status_icon} **{e.event_name}**\n      └ {start_dt} — {end_dt}")

        await message.answer("\n".join(response), parse_mode="Markdown")


@router.message(Command("create_event"))
async def cmd_create_event(message: types.Message, state: FSMContext):
    await message.answer("Введите название события")
    await state.set_state(CreateEvent.name)


@router.message(CreateEvent.name)
async def create_event_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите дату и время события в формате ДД.ММ.ГГГГ ЧЧ:ММ")
    await state.set_state(CreateEvent.start)


@router.message(CreateEvent.start)
async def create_event_start(message: types.Message, state: FSMContext):
    date, time = message.text.split()
    try:
        date_start = datetime.strptime(date, '%d.%m.%Y').date()
        time_start = datetime.strptime(time, '%H:%M').time()
    except ValueError:
        await message.answer("Неверный формат даты или времени.")
        return

    await state.update_data(start_date=date_start, time_start=time_start)
    await message.answer(
        "Введите дату окончания события в формате ДД.ММ.ГГГГ ЧЧ:ММ, если событие длится один день, то введите только время")
    await state.set_state(CreateEvent.end)


@router.message(CreateEvent.end)
async def create_event_end(message: types.Message, state: FSMContext):
    date = message.text.split()
    data = await state.get_data()
    try:
        if len(date) == 1:
            date_end = data['start_date']
            time_end = datetime.strptime(date[0], '%H:%M').time()
        else:
            date_end = datetime.strptime(date[0], '%d.%m.%Y').date()
            time_end = datetime.strptime(date[1], '%H:%M').time()
        if date_end < data['start_date'] or time_end < data['time_start']:
            await message.answer("Дата окончания события не может быть раньше даты начала.")
            return
        await state.update_data(date_end=date_end, time_end=time_end)
    except ValueError:
        await message.answer("Неверный формат даты или времени.")
        return
    data = await state.get_data()
    await message.answer(f"Название: {data['name']}\n"
                         f"Дата начала: {data['start_date']} {data['time_start'].strftime('%H:%M')}\n"
                         f"Дата окончания: {data['date_end']} {data['time_end'].strftime('%H:%M')}\n"
                         f"Все верно? Да/Нет")
    await state.set_state(CreateEvent.chose)


@router.message(CreateEvent.chose)
async def create_event_chose(message: types.Message, state: FSMContext):
    if message.text.lower() == "да":
        data = await state.get_data()
        with SessionLocal() as db:
            user = db.query(User).filter(User.telegram_id == str(message.from_user.id)).first()

            if user:
                new_event = Event(
                    user_id=user.id,
                    event_name=data['name'],
                    start_date=data['start_date'],
                    time_start=data['time_start'],
                    end_date=data['date_end'],
                    time_end=data['time_end'],
                    notify_at=datetime.combine(data['start_date'], data['time_start']),
                    is_completed=0
                )
                db.add(new_event)
                db.commit()
        await message.answer("Событие успешно создано.")
        await state.clear()
        return
    elif message.text.lower() == "нет":
        await message.answer("Введите название события")
        await state.set_state(CreateEvent.name)


# -------------------------------------------------------------------
# Логика задач
# -------------------------------------------------------------------


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


@router.message(Command("create_task"))
async def cmd_create_task(message: types.Message, state: FSMContext):
    await message.answer("Введите название задачи")
    await state.set_state(CreateTask.name)


@router.message(CreateTask.name)
async def create_task_name(message: types.Message, state: FSMContext):
    await message.answer("Введите описание задачи, если его нет напишите 'нет'")
    await state.update_data(name=message.text)
    await state.set_state(CreateTask.description)


@router.message(CreateTask.description)
async def create_task_description(message: types.Message, state: FSMContext):
    if message.text.lower() == "нет":
        await state.update_data(description="")
    else:
        await state.update_data(description=message.text)
    await message.answer("Введите номер категории задачи\n"
                         "1. Срочно и важно\n"
                         "2. Важно, но не срочно\n"
                         "3. Срочно, но не важно\n"
                         "4. Не срочно и не важно")
    await state.set_state(CreateTask.category)


@router.message(CreateTask.category)
async def create_task_category(message: types.Message, state: FSMContext):
    category = {1: "Срочно и важно", 2: "Важно, но не срочно", 3: "Срочно, но не важно", 4: "Не срочно и не важно"}
    try:
        await state.update_data(category=category[int(message.text)])
    except ValueError:
        await message.answer("Неверный формат категории.")
        return
    data = await state.get_data()
    await message.answer(f"Название: {data['name']}\n"
                         f"Описание: {data['description']}\n"
                         f"Категория: {data['category']}\n"
                         f"Все верно? Да/Нет")
    await state.set_state(CreateTask.check)


@router.message(CreateTask.check)
async def create_task_check(message: types.Message, state: FSMContext):
    if message.text.lower() == "да":
        data = await state.get_data()
        with SessionLocal() as db:
            user = db.query(User).filter(User.telegram_id == str(message.from_user.id)).first()
            if user:
                new_task = Task(
                    user_id=user.id,
                    name=data['name'],
                    description=data['description'],
                    category=data['category'],
                    is_completed=0
                )
                db.add(new_task)
                db.commit()
        await message.answer("Задача успешно создана.")
        await state.clear()
        return
    elif message.text.lower() == "нет":
        await message.answer("Введите название задачи")
        await state.set_state(CreateTask.name)
