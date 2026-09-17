from contextlib import nullcontext
import sqlite3

from . import api


def get_user(
    auth_issuer: str, auth_subject: str, connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return the account associated with an OIDC identity.

    Params
    ----------
    auth_issuer : str
        OIDC provider that authenticated the user.
    auth_subject : str
        Stable user identifier supplied by the OIDC provider.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    dict or None
        Matching user row, or ``None`` when the identity is unknown.
    """

    # Match the provider and its stable user identifier; never create on lookup.
    users = api.get(
        table="users",
        filters={"auth_issuer": auth_issuer, "auth_subject": auth_subject},
        connection=connection,
    )
    return users[0] if users else None


def get_users(connection: sqlite3.Connection | None = None) -> list[dict] | None:
    """Return every registered user ordered by database identifier.

    Params
    ----------
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    list of dict
        Registered user rows, or an empty list when no users exist.
    """
    users = api.get(
        table="users",
        connection=connection,
    )
    return users


def set_user(
    auth_issuer: str, auth_subject: str, username: str,
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Create or rename the account associated with a verified identity.

    Params
    ----------
    auth_issuer : str
        OIDC provider that authenticated the user.
    auth_subject : str
        Stable user identifier supplied by the OIDC provider.
    username : str
        Application username to store after trimming whitespace.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    dict
        Newly created or updated user row.
    """

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
                "users",
                {
                    "auth_issuer": auth_issuer,
                    "auth_subject": auth_subject,
                    "username": username,
                },
                connection=conn,
            )
        else:
            api.update(
                "users",
                {"username": username},
                {"id": user["id"]},
                connection=conn,
            )

        return get_user(auth_issuer, auth_subject, connection=conn)
