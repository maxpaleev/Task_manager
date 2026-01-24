from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, time


class EventCreate(BaseModel):
    event_name: str
    start_date: date
    end_date: date
    time_start: time
    time_end: time
    is_completed: int
    notify_at: datetime


class LinkCode(BaseModel):
    code: str


class TaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    is_completed: int


class EventResponse(EventCreate):
    id: int
    user_id: int

    class Config:
        from_attributes = True


class EventUpdate(BaseModel):
    is_completed: Optional[int] = None


class TaskResponse(TaskCreate):
    id: int
    user_id: int

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    is_completed: Optional[int] = None
