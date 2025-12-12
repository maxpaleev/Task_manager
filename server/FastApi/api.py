from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from DB.database import get_db
from DB.models import Event
from .schemas import EventCreate

router = APIRouter()

@router.post("/events")
def add_event(
        event_data: EventCreate,
        db: Session = Depends(get_db)):
    try:
        notify_datatime = datetime.strptime(event_data.notify_at_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD HH:MM:SS")

    new_event = Event(
        user_id=event_data.user_id,
        text=event_data.text,
        start_time=notify_datatime,
        is_sent=False
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return {"status": "success", "message": "Событие сохранено, будет отправлено по расписанию.", "id": new_event.id}