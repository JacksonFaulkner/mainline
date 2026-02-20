from __future__ import annotations

from uuid import uuid4

from app.api.deps import get_current_user
from app.main import app
from app.models import User


def _test_user_override() -> User:
    return User(
        id=uuid4(),
        email="chess-tests@example.com",
        full_name="Chess Test User",
        hashed_password="unused",
        is_active=True,
        is_superuser=True,
    )


def enable_auth_override() -> None:
    app.dependency_overrides[get_current_user] = _test_user_override


def disable_auth_override() -> None:
    app.dependency_overrides.pop(get_current_user, None)
