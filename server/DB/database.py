from sqlalchemy import  create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "postgresql://postgres:6299@localhost:5432/planner"

engine = create_engine(SQLALCHEMY_DATABASE_URL,
                       pool_pre_ping=True,
                       echo=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()