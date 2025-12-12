from DB.database import engine, Base
from DB.models import User, Event

def create_tables():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_tables()