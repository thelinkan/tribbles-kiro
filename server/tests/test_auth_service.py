"""Tests for the Auth_Service (registration, login, token management).

Uses an in-memory mock of the aiomysql pool to test auth logic without
requiring a live database connection.
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import bcrypt
from auth.service import AuthService, AuthError, SESSION_DURATION_HOURS


class FakeCursor:
    """A fake async cursor that stores data in memory."""

    def __init__(self, storage: dict):
        self._storage = storage
        self._last_result = None
        self._lastrowid = 0

    @property
    def lastrowid(self):
        return self._lastrowid

    async def execute(self, query: str, args=None):
        query_lower = query.strip().lower()

        if query_lower.startswith("insert into players"):
            username, password_hash, email = args
            # Check for duplicate username
            for pid, player in self._storage.get("players", {}).items():
                if player["username"] == username:
                    import aiomysql
                    raise aiomysql.IntegrityError("Duplicate entry")
            # Insert new player
            players = self._storage.setdefault("players", {})
            new_id = len(players) + 1
            players[new_id] = {
                "username": username,
                "password_hash": password_hash,
                "email": email,
                "created_at": datetime.now(timezone.utc),
            }
            self._lastrowid = new_id

        elif query_lower.startswith("select player_id, password_hash from players"):
            username = args[0]
            for pid, player in self._storage.get("players", {}).items():
                if player["username"] == username:
                    self._last_result = (pid, player["password_hash"])
                    return
            self._last_result = None

        elif query_lower.startswith("insert into sessions"):
            token, player_id, created_at, expires_at = args
            sessions = self._storage.setdefault("sessions", {})
            sessions[token] = {
                "player_id": player_id,
                "created_at": created_at,
                "expires_at": expires_at,
            }

        elif query_lower.startswith("select player_id, expires_at from sessions"):
            token = args[0]
            session = self._storage.get("sessions", {}).get(token)
            if session:
                self._last_result = (session["player_id"], session["expires_at"])
            else:
                self._last_result = None

        elif query_lower.startswith("delete from sessions"):
            token = args[0]
            sessions = self._storage.get("sessions", {})
            sessions.pop(token, None)

    async def fetchone(self):
        return self._last_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeConnection:
    """A fake async connection wrapping a FakeCursor."""

    def __init__(self, storage: dict):
        self._storage = storage
        self._cursor = FakeCursor(storage)

    def cursor(self):
        return self._cursor

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakePool:
    """A fake aiomysql pool that returns FakeConnections."""

    def __init__(self):
        self._storage: dict = {}

    def acquire(self):
        return FakeConnection(self._storage)


@pytest.fixture
def auth_service():
    """Create an AuthService with a fake in-memory pool."""
    pool = FakePool()
    return AuthService(pool)


class TestRegister:
    """Tests for AuthService.register."""

    @pytest.mark.asyncio
    async def test_register_success(self, auth_service):
        player_id, error = await auth_service.register("alice", "password123", "alice@example.com")
        assert player_id is not None
        assert player_id == 1
        assert error is None

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        player_id, error = await auth_service.register("alice", "other_pass", "alice2@example.com")
        assert player_id is None
        assert error is not None
        assert error.code == "username_taken"

    @pytest.mark.asyncio
    async def test_register_hashes_password(self, auth_service):
        await auth_service.register("bob", "mysecret", "bob@example.com")
        # Verify the stored hash is a valid bcrypt hash
        storage = auth_service._pool._storage
        player = storage["players"][1]
        assert player["password_hash"] != "mysecret"
        assert bcrypt.checkpw(b"mysecret", player["password_hash"].encode("utf-8"))

    @pytest.mark.asyncio
    async def test_register_multiple_users(self, auth_service):
        pid1, _ = await auth_service.register("user1", "pass1", "u1@example.com")
        pid2, _ = await auth_service.register("user2", "pass2", "u2@example.com")
        assert pid1 == 1
        assert pid2 == 2


class TestLogin:
    """Tests for AuthService.login."""

    @pytest.mark.asyncio
    async def test_login_success(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, error = await auth_service.login("alice", "password123")
        assert token is not None
        assert len(token) > 0
        assert error is None

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, error = await auth_service.login("alice", "wrongpassword")
        assert token is None
        assert error is not None
        assert error.code == "auth_failed"
        assert "Invalid username or password" in error.message

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, auth_service):
        token, error = await auth_service.login("nobody", "password123")
        assert token is None
        assert error is not None
        assert error.code == "auth_failed"
        assert "Invalid username or password" in error.message

    @pytest.mark.asyncio
    async def test_login_generic_error_same_for_bad_user_and_bad_password(self, auth_service):
        """Requirement 1.5: error must not reveal which field is incorrect."""
        await auth_service.register("alice", "password123", "alice@example.com")

        # Bad username
        _, err_user = await auth_service.login("nonexistent", "password123")
        # Bad password
        _, err_pass = await auth_service.login("alice", "wrongpassword")

        # Both should have the same error code and message format
        assert err_user.code == err_pass.code
        assert err_user.message == err_pass.message

    @pytest.mark.asyncio
    async def test_login_creates_session(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, _ = await auth_service.login("alice", "password123")
        # Verify session was stored
        storage = auth_service._pool._storage
        assert token in storage["sessions"]
        session = storage["sessions"][token]
        assert session["player_id"] == 1


class TestValidateToken:
    """Tests for AuthService.validate_token."""

    @pytest.mark.asyncio
    async def test_validate_valid_token(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, _ = await auth_service.login("alice", "password123")
        player_id, error = await auth_service.validate_token(token)
        assert player_id == 1
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_invalid_token(self, auth_service):
        player_id, error = await auth_service.validate_token("nonexistent_token")
        assert player_id is None
        assert error is not None
        assert error.code == "unauthorised"

    @pytest.mark.asyncio
    async def test_validate_expired_token(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, _ = await auth_service.login("alice", "password123")

        # Manually expire the token
        storage = auth_service._pool._storage
        storage["sessions"][token]["expires_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        player_id, error = await auth_service.validate_token(token)
        assert player_id is None
        assert error is not None
        assert error.code == "unauthorised"

    @pytest.mark.asyncio
    async def test_validate_expired_token_is_cleaned_up(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, _ = await auth_service.login("alice", "password123")

        # Manually expire the token
        storage = auth_service._pool._storage
        storage["sessions"][token]["expires_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        await auth_service.validate_token(token)
        # Token should be removed from storage
        assert token not in storage["sessions"]


class TestInvalidateToken:
    """Tests for AuthService.invalidate_token."""

    @pytest.mark.asyncio
    async def test_invalidate_removes_session(self, auth_service):
        await auth_service.register("alice", "password123", "alice@example.com")
        token, _ = await auth_service.login("alice", "password123")

        await auth_service.invalidate_token(token)

        # Token should no longer validate
        player_id, error = await auth_service.validate_token(token)
        assert player_id is None
        assert error is not None
        assert error.code == "unauthorised"

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_token_no_error(self, auth_service):
        # Should not raise any exception
        await auth_service.invalidate_token("nonexistent_token")
