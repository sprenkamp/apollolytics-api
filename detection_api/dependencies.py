from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from database.postgres import SessionLocal
from database.repo import Repo


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def repo(db: Session = Depends(get_db)) -> Repo:
    return Repo(db)
