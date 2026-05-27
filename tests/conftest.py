"""Konfiguracja pytest – baza in-memory SQLite, klient testowy FastAPI."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.utils.security import create_access_token, hash_password

TEST_DB_URL = "sqlite:///./test_podaruj.db"

engine_test = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture()
def db():
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def make_user(db, email: str, password: str = "haslo1234",
              first_name: str = "Jan", last_name: str = "Kowalski",
              active: bool = True) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}
