"""Database operations for the ``persistent_state`` table."""

import sqlite3

from . import db_api


TABLE_NAME = "persistent_state"


def get_persistent_state(
    user_id: int,
    page_name: str,
    key: str,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one persisted value identified by user, page and key.

    Params
    ----------
    user_id : int
        Identifier of the value owner.
    page_name : str
        Page that owns the persistent key.
    key : str
        Exact persistent-state key.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict or None
        Matching row, or ``None`` when it does not exist.
    """
    rows = get_persistent_states(
        {"user_id": user_id, "page_name": page_name, "key": key},
        connection=connection,
    )
    return rows[0] if rows else None


def get_persistent_states(
    filters: dict[str, db_api.SQLValue] | None = None,
    proj: list[str] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return persisted values matching all optional equality filters.

    Params
    ----------
    filters : dict or None
        Column/value conditions, or ``None`` to return every row.
    proj : list of str or None
        Columns to return, or ``None`` to return every column.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    list of dict
        Matching persisted values in deterministic order.
    """
    return db_api.get(TABLE_NAME, filters, proj, connection=connection)


def set_persistent_state(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert one persisted value and return the stored row.

    Params
    ----------
    data : dict
        Row fields including user, page, key and JSON value.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict
        Inserted persistent-state row.
    """
    db_api.insert(TABLE_NAME, data, connection=connection)
    return get_persistent_state(
        int(data["user_id"]),
        str(data["page_name"]),
        str(data["key"]),
        connection=connection,
    )


def update_persistent_state(
    user_id: int,
    page_name: str,
    key: str,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one persisted value selected by its composite key.

    Params
    ----------
    user_id : int
        Identifier of the value owner.
    page_name : str
        Page that owns the persistent key.
    key : str
        Exact persistent-state key.
    data : dict
        Columns and new values to store.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict or None
        Updated row, or ``None`` when it does not exist.
    """
    filters = {"user_id": user_id, "page_name": page_name, "key": key}
    db_api.update(TABLE_NAME, data, filters, connection=connection)
    return get_persistent_state(user_id, page_name, key, connection=connection)


def rm_persistent_states(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove persisted values matching all required filters.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting rows to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed rows.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
