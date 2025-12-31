import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from server.DB.database import get_db
from server.DB.models import Event, User, Task
from .schemas import EventCreate, LinkCode, TaskCreate

router = APIRouter()


def get_current_user(
        db: Session = Depends(get_db),
        authorization: Annotated[str, Header(alias='Authorization')] = None
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split(" ")[1] if authorization.startswith("Bearer ") else authorization
    user = db.query(User).filter(User.api_token == token).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


AuthenticatedUser = Depends(get_current_user)


@router.post("/auth/link")
def link_device(link_data: LinkCode, db: Session = Depends(get_db)):
    """Обмен временного кода из бота на постоянный API токен."""
    user = db.query(User).filter(User.link_code == link_data.code).first()
    if not user:
        raise HTTPException(status_code=404, detail="Код не найден")

    new_token = str(uuid.uuid4())
    user.api_token = new_token
    user.link_code = None  # Сбрасываем код после использования
    db.commit()
    return {"status": "success", "api_token": new_token}


@router.post("/events")
def create_event(
        event_data: EventCreate,
        current_user: User = AuthenticatedUser,
        db: Session = Depends(get_db)
):
    """Создание события с привязкой к пользователю."""
    new_event = Event(
        user_id=current_user.id,
        event_name=event_data.event_name,
        start_date=event_data.start_date,
        end_date=event_data.end_date,
        time_start=event_data.time_start,
        time_end=event_data.time_end,
        notify_at=event_data.notify_at,
        is_completed=event_data.is_completed
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return {"status": "success", "id": new_event.id}


@router.delete("/events/{event_id}")
def delete_event(
        event_id: int,
        current_user: User = AuthenticatedUser,
        db: Session = Depends(get_db)
):
    """Удаление события по ID сервера."""
    event = db.query(Event).filter(Event.id == event_id, Event.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    db.delete(event)
    db.commit()
    return {"status": "success"}

@router.post("/tasks")
def create_task(
        task_data: TaskCreate,
        current_user: User = AuthenticatedUser,
        db: Session = Depends(get_db)
):
    new_task = Task(
        user_id=current_user.id,
        name=task_data.name,
        description=task_data.description,
        category=task_data.category,
        is_completed=task_data.is_completed
    )
    db.add(new_task)
    db.commit()
    return {"status": "success", "id": new_task.id}
