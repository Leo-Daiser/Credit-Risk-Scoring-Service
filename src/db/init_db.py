from src.db.base import Base
from src.db.session import engine
from src.db import models  # noqa: F401

def init_db() -> None:
    Base.metadata.create_all(bind=engine)