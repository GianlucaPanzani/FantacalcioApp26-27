"""Database operations for the ``users`` table."""

import sqlite3

from . import db_api


TABLE_NAME = "users"


def get_user(
    user_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one user by identifier, or ``None`` when it does not exist."""
    users = get_users({"id": user_id}, connection=connection)
    return users[0] if users else None


def get_users(
    filters: dict[str, db_api.SQLValue] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return users matching all optional equality filters.

    Params
    ----------
    filters : dict or None
        Column/value conditions, or ``None`` to return every user.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    list of dict
        Matching users ordered by identifier.
    """
    return db_api.get(TABLE_NAME, filters, connection=connection)


def set_user(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert a user from a column/value dictionary and return the stored row.

    Params
    ----------
    data : dict
        User fields to insert, including ``username`` and ``team_name``.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict
        Inserted user row.
    """
    user_id = db_api.insert(TABLE_NAME, data, connection=connection)
    return get_user(user_id, connection=connection)


def update_user(
    user_id: int,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one user by identifier and return the resulting row.

    Params
    ----------
    user_id : int
        Identifier of the user to update.
    data : dict
        Columns and new values to store.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict or None
        Updated user, or ``None`` when the identifier does not exist.
    """
    db_api.update(TABLE_NAME, data, {"id": user_id}, connection=connection)
    return get_user(user_id, connection=connection)


def rm_users(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove users matching all filters and return the affected row count.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting the users to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed users.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
