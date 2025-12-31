from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Date, Time
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    # Сделано nullable=True, чтобы пользователь мог быть создан ботом до получения токена
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    api_token = Column(String, unique=True, index=True, nullable=True) # Добавлено nullable=True
    link_code = Column(String, unique=True, nullable=True)
    events = relationship("Event", back_populates="owner")
    tasks = relationship("Task", back_populates="owner")

class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    event_name = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    time_start = Column(Time)
    time_end = Column(Time)
    notify_at = Column(DateTime)
    is_sent = Column(Boolean, default=0)
    is_completed = Column(Integer, default=False)
    owner = relationship("User", back_populates="events")

class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)
    is_completed = Column(Boolean, default=False)
    owner = relationship("User", back_populates="tasks")