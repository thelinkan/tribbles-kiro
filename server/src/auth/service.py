"""Authentication service for player registration and session management.

Provides registration, login, token validation, and token invalidation
using bcrypt for password hashing and aiomysql for database access.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import aiomysql
import bcrypt


class AuthError:
    """Represents an authentication error with a code and message."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"AuthError(code={self.code!r}, message={self.message!r})"


# Type aliases for Result pattern
# Success: (value, None)  |  Failure: (None, AuthError)
PlayerID = int
SessionToken = str

# Session token validity duration
SESSION_DURATION_HOURS = 24


class AuthService:
    """Handles player registration, login, and session token management.

    Uses bcrypt for password hashing and generates cryptographically secure
    session tokens stored in the database with expiration timestamps.
    """

    def __init__(self, pool: aiomysql.Pool):
        """Initialise the auth service with a database connection pool.

        Args:
            pool: An aiomysql connection pool for database access.
        """
        self._pool = pool

    async def register(
        self, username: str, password: str, email: str
    ) -> Tuple[Optional[PlayerID], Optional[AuthError]]:
        """Register a new player account.

        Hashes the password with bcrypt and inserts a new player record.

        Args:
            username: Unique username for the player.
            password: Plain-text password to be hashed.
            email: Player's email address.

        Returns:
            A tuple of (player_id, None) on success, or (None, AuthError) on failure.
        """
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        "INSERT INTO players (username, password_hash, email) "
                        "VALUES (%s, %s, %s)",
                        (username, password_hash, email),
                    )
                    await conn.commit()
                    player_id = cur.lastrowid
                    return (player_id, None)
                except aiomysql.IntegrityError:
                    await conn.rollback()
                    return (
                        None,
                        AuthError("username_taken", "Username is already taken."),
                    )

    async def login(
        self, username: str, password: str
    ) -> Tuple[Optional[SessionToken], Optional[AuthError]]:
        """Authenticate a player and create a session.

        Verifies credentials against the database and generates a session token.
        Returns a generic error on failure without revealing which field is incorrect.

        Args:
            username: The player's username.
            password: The player's plain-text password.

        Returns:
            A tuple of (session_token, None) on success, or (None, AuthError) on failure.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT player_id, password_hash FROM players WHERE username = %s",
                    (username,),
                )
                row = await cur.fetchone()

                if row is None:
                    # Username not found — return generic error
                    return (
                        None,
                        AuthError(
                            "auth_failed",
                            "Invalid username or password.",
                        ),
                    )

                player_id, stored_hash = row

                if not bcrypt.checkpw(
                    password.encode("utf-8"), stored_hash.encode("utf-8")
                ):
                    # Password mismatch — return same generic error
                    return (
                        None,
                        AuthError(
                            "auth_failed",
                            "Invalid username or password.",
                        ),
                    )

                # Generate session token and store it
                token = secrets.token_urlsafe(64)
                now = datetime.now(timezone.utc)
                expires_at = now + timedelta(hours=SESSION_DURATION_HOURS)

                await cur.execute(
                    "INSERT INTO sessions (token, player_id, created_at, expires_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (token, player_id, now, expires_at),
                )
                await conn.commit()

                return (token, None)

    async def validate_token(
        self, token: str
    ) -> Tuple[Optional[PlayerID], Optional[AuthError]]:
        """Validate a session token and return the associated player ID.

        Checks that the token exists in the sessions table and has not expired.

        Args:
            token: The session token to validate.

        Returns:
            A tuple of (player_id, None) on success, or (None, AuthError) on failure.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT player_id, expires_at FROM sessions WHERE token = %s",
                    (token,),
                )
                row = await cur.fetchone()

                if row is None:
                    return (
                        None,
                        AuthError("unauthorised", "Invalid or expired session token."),
                    )

                player_id, expires_at = row

                # Ensure expires_at is timezone-aware for comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                if datetime.now(timezone.utc) >= expires_at:
                    # Token has expired — clean it up
                    await cur.execute(
                        "DELETE FROM sessions WHERE token = %s", (token,)
                    )
                    await conn.commit()
                    return (
                        None,
                        AuthError("unauthorised", "Invalid or expired session token."),
                    )

                return (player_id, None)

    async def invalidate_token(self, token: str) -> None:
        """Invalidate a session token by removing it from the database.

        Args:
            token: The session token to invalidate.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM sessions WHERE token = %s", (token,)
                )
                await conn.commit()
