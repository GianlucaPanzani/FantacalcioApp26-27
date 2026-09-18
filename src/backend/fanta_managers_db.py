"""Database operations and registration flow for ``fanta_managers``."""

import sqlite3
from . import db_api


TABLE_NAME = "fanta_managers"


def get_fanta_manager(
    fanta_manager_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one Fanta Manager by identifier, or ``None`` when absent."""
    fanta_managers = get_fanta_managers(
        {"id": fanta_manager_id},
        connection=connection,
    )
    return fanta_managers[0] if fanta_managers else None


def get_fanta_managers(
    filters: dict[str, db_api.SQLValue] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return Fanta Managers matching all optional equality filters."""
    return db_api.get(TABLE_NAME, filters, connection=connection)


def set_fanta_manager(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert a Fanta Manager from a column/value dictionary and return it."""
    fanta_manager_id = db_api.insert(TABLE_NAME, data, connection=connection)
    return get_fanta_manager(fanta_manager_id, connection=connection)


def update_fanta_manager(
    fanta_manager_id: int,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one Fanta Manager by identifier and return the resulting row."""
    db_api.update(
        TABLE_NAME,
        data,
        {"id": fanta_manager_id},
        connection=connection,
    )
    return get_fanta_manager(fanta_manager_id, connection=connection)


def rm_fanta_managers(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove Fanta Managers matching all filters.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting the rows to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed Fanta Managers.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
