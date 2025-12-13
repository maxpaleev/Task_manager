from pydantic import BaseModel
from datetime import datetime

class EventCreate(BaseModel):
    text: str
    # Pydantic сам распарсит строку "YYYY-MM-DD HH:MM:SS" в объект datetime
    notify_at: datetime

class LinkCode(BaseModel):
    code: str