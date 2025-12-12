from pydantic import BaseModel, field_validator
from datetime import datetime


class EventCreate(BaseModel):
    # user_id удален, так как теперь он берется из токена в API.

    # Текст напоминания
    text: str

    # Дата и время в виде строки (например, "2025-12-15 14:30:00")
    notify_at_str: str

    @field_validator('notify_at_str')
    @classmethod
    def validate_datetime_format(cls, value):
        try:
            # Проверяем, что строка соответствует ожидаемому формату
            datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError("Неверный формат даты/времени. Ожидается YYYY-MM-DD HH:MM:SS")
        return value


class LinkCode(BaseModel):
    code: str