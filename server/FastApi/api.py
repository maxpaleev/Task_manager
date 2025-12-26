import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import datetime

from DB.database import get_db
from DB.models import Event, User
from .schemas import EventCreate, LinkCode

router = APIRouter()


def get_current_user(
        db: Session = Depends(get_db),
        authorization: Annotated[str, Header(alias='Authorization', description='API Token')] = None
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Требуется заголовок Authorization.")

    # ИСПРАВЛЕНО: Более безопасное извлечение токена (с учетом "Bearer ")
    if authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = authorization

    # ИСПРАВЛЕНО: Проверка по правильному полю модели
    user = db.query(User).filter(User.api_token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Неверный или просроченный токен.")
    return user


AuthenticatedUser = Depends(get_current_user)


@router.post("/auth/link")
def exchange_code_for_token(link_data: LinkCode, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.link_code == link_data.code).first()

    if not user:
        raise HTTPException(status_code=404, detail="Код связывания не найден или недействителен.")

    new_token = str(uuid.uuid4())

    user.api_token = new_token
    user.link_code = None
    db.commit()

    return {"status": "success", "api_token": new_token}


@router.post("/events")
def add_event(
        event_data: EventCreate,
        current_user: User = AuthenticatedUser,  # Получаем пользователя из токена
        db: Session = Depends(get_db)):
    # ИСПРАВЛЕНО: user_id берется из аутентифицированного пользователя

    new_event = Event(
        user_id=current_user.id,  # ИСПРАВЛЕНО
        event_name=event_data.event_name,
        start_date=event_data.start_date,
        end_date=event_data.end_date,
        time_start=event_data.time_start,
        time_end=event_data.time_end,
        notify_at=event_data.notify_at,
        is_completed=0,
        is_sent=False
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    # Возвращаем ID, присвоенный сервером, для синхронизации на клиенте
    return {"status": "success", "message": "Событие сохранено, будет отправлено по расписанию.", "id": new_event.id}

@router.delete("/events/{event_id}")
def delete_event(
        event_id: int,
        current_user: User = AuthenticatedUser,
        db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id, Event.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено или не принадлежит пользователю.")

    db.delete(event)
    db.commit()

    return {"status": "success", "message": f"Событие ID {event_id} удалено."}
