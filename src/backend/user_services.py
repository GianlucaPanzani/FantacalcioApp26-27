from contextlib import nullcontext
import sqlite3

from . import api


def get_user(
    auth_issuer: str, auth_subject: str, *, connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return the account associated with an OIDC identity, or None if absent."""

    # Match the provider and its stable user identifier; never create on lookup.
    users = api.get(
        "users",
        ["auth_issuer", "auth_subject"],
        [auth_issuer, auth_subject],
        connection=connection,
    )
    return users[0] if users else None


def set_user(
    auth_issuer: str, auth_subject: str, username: str, *, connection: sqlite3.Connection | None = None,
) -> dict:
    """Create or rename the account for a verified identity and return its row."""

    # Trim form input; uniqueness is enforced by the database.
    username = username.strip()
    if not username:
        raise ValueError("Enter a username.")

    # Reuse the registration transaction, or open one for a standalone save.
    context = api.transaction() if connection is None else nullcontext(connection)
    with context as conn:
        user = get_user(auth_issuer, auth_subject, connection=conn)
        if user is None:
            api.insert(
                "users", ["auth_issuer", "auth_subject", "username"],
                [auth_issuer, auth_subject, username], connection=conn,
            )
        else:
            api.update("users", "username", username, where={"id": user["id"]}, connection=conn)

        return get_user(auth_issuer, auth_subject, connection=conn)
