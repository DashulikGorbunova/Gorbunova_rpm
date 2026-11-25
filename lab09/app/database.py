from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def make_session_factory(url):
    return sessionmaker(bind=create_engine(url, pool_pre_ping=True), expire_on_commit=False)
