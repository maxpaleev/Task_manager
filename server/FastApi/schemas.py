from pydantic import BaseModel
from datetime import datetime

class EventCreate(BaseModel):
    event_name: str
    event_start: datetime
    event_end: datetime
    time_start: datetime
    time_end: datetime
    notify_at: datetime

class LinkCode(BaseModel):
    code: str