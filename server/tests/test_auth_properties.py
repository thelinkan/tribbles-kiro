"""Property-based tests for the Auth_Service.

Uses Hypothesis to verify correctness properties across many random inputs.
Tests use the same FakeCursor/FakeConnection/FakePool pattern as the unit tests
for in-memory testing without a live database.

**Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**
"""

import asyncio
import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from auth.service import AuthService, AuthError


# ---------------------------------------------------------------------------
# Fake DB infrastructure (same pattern as test_auth_service.py)
# ---------------------------------------------------------------------------

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
            for pid, player in self._storage.get("players", {}).items():
                if player["username"] == username:
                    import aiomysql
                    raise aiomysql.IntegrityError("Duplicate entry")
            players = self._storage.setdefault("players", {})
            new_id = len(players) + 1
            players[new_id] = {
                "username": username,
                "password_hash": password_hash,
                "email": email,
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


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid auth inputs
# ---------------------------------------------------------------------------

# Usernames: printable ASCII characters (no whitespace), 1-30 chars
valid_usernames = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=30,
)

# Passwords: printable ASCII, 1-50 chars
valid_passwords = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=50,
)

# Emails: simple valid-looking email addresses
valid_emails = st.from_regex(r"[a-z][a-z0-9]{0,10}@[a-z]{2,8}\.[a-z]{2,4}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 1: Registration and login round-trip
# ---------------------------------------------------------------------------

class TestRegistrationLoginRoundTrip:
    """**Validates: Requirements 1.2, 1.3, 1.4**

    For any valid username, password, and email combination where the username
    is not already taken, registering then logging in with the same username
    and password should return a valid session token; and registering a second
    time with the same username should return a "username taken" error.
    """

    @given(username=valid_usernames, password=valid_passwords, email=valid_emails)
    @settings(max_examples=50)
    def test_register_then_login_returns_valid_token(self, username, password, email):
        """Registering a new user and logging in should yield a session token."""

        async def _run():
            service = AuthService(FakePool())

            # Register should succeed
            player_id, error = await service.register(username, password, email)
            assert error is None, f"Registration failed unexpectedly: {error}"
            assert player_id is not None

            # Login with same credentials should succeed
            token, error = await service.login(username, password)
            assert error is None, f"Login failed unexpectedly: {error}"
            assert token is not None
            assert len(token) > 0

            # Token should be valid
            validated_id, error = await service.validate_token(token)
            assert error is None
            assert validated_id == player_id

        asyncio.run(_run())

    @given(username=valid_usernames, password=valid_passwords, email=valid_emails)
    @settings(max_examples=50)
    def test_duplicate_registration_returns_username_taken(self, username, password, email):
        """Registering the same username twice should return a username_taken error."""

        async def _run():
            service = AuthService(FakePool())

            # First registration succeeds
            player_id, error = await service.register(username, password, email)
            assert error is None

            # Second registration with same username should fail
            player_id2, error2 = await service.register(username, "different_pass", "other@test.com")
            assert player_id2 is None
            assert error2 is not None
            assert error2.code == "username_taken"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 2: Invalid login does not reveal which field is wrong
# ---------------------------------------------------------------------------

class TestInvalidLoginGenericError:
    """**Validates: Requirements 1.5**

    For any login attempt with either an invalid username or an incorrect
    password, the Auth_Service should return the same error response format
    without distinguishing which field caused the failure.
    """

    @given(
        username=valid_usernames,
        password=valid_passwords,
        email=valid_emails,
        wrong_password=valid_passwords,
        fake_username=valid_usernames,
    )
    @settings(max_examples=50)
    def test_wrong_password_and_wrong_username_same_error(
        self, username, password, email, wrong_password, fake_username
    ):
        """Error for wrong password must be identical to error for wrong username."""
        # Ensure the wrong password is actually different
        assume(wrong_password != password)
        # Ensure the fake username is different from the real one
        assume(fake_username != username)

        async def _run():
            service = AuthService(FakePool())

            # Register a user
            await service.register(username, password, email)

            # Attempt login with correct username but wrong password
            token_bad_pass, err_bad_pass = await service.login(username, wrong_password)
            assert token_bad_pass is None
            assert err_bad_pass is not None

            # Attempt login with non-existent username
            token_bad_user, err_bad_user = await service.login(fake_username, password)
            assert token_bad_user is None
            assert err_bad_user is not None

            # Both errors must have the same code and message (no information leakage)
            assert err_bad_pass.code == err_bad_user.code
            assert err_bad_pass.message == err_bad_user.message

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 3: Invalidated token is rejected
# ---------------------------------------------------------------------------

class TestInvalidatedTokenRejected:
    """**Validates: Requirements 1.6**

    For any valid session token that has been invalidated, all subsequent
    requests using that token should be rejected with an unauthorised error.
    """

    @given(username=valid_usernames, password=valid_passwords, email=valid_emails)
    @settings(max_examples=50)
    def test_invalidated_token_is_rejected(self, username, password, email):
        """After invalidation, the token must be rejected with unauthorised error."""

        async def _run():
            service = AuthService(FakePool())

            # Register and login to get a valid token
            await service.register(username, password, email)
            token, error = await service.login(username, password)
            assert error is None
            assert token is not None

            # Token should be valid before invalidation
            player_id, error = await service.validate_token(token)
            assert error is None
            assert player_id is not None

            # Invalidate the token
            await service.invalidate_token(token)

            # Token should now be rejected
            player_id, error = await service.validate_token(token)
            assert player_id is None
            assert error is not None
            assert error.code == "unauthorised"

        asyncio.run(_run())
