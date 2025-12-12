from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
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

class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    text = Column(String)
    start_time = Column(DateTime)
    is_sent = Column(Boolean, default=False)
    owner = relationship("User", back_populates="events")