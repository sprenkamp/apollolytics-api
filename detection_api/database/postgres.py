import os

from dotenv import load_dotenv

load_dotenv()
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = os.getenv("POSTGRES_URL")


def setup(database_uri):
    engine = create_engine(database_uri, pool_pre_ping=True, client_encoding='utf8')
    return sessionmaker(autocommit=False, autoflush=False, bind=engine), engine


SessionLocal, engine = setup(database_uri=POSTGRES_URL)
