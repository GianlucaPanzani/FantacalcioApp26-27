"""Database operations for the ``purchases`` table."""

import sqlite3

from . import db_api


TABLE_NAME = "purchases"


def get_purchase(
    purchase_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one purchase by identifier, or ``None`` when it does not exist."""
    purchases = get_purchases({"id": purchase_id}, connection=connection)
    return purchases[0] if purchases else None


def get_purchases(
    filters: dict[str, db_api.SQLValue] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return purchases matching all optional equality filters."""
    return db_api.get(TABLE_NAME, filters, connection=connection)


def set_purchase(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert a purchase from a column/value dictionary and return it."""
    purchase_id = db_api.insert(TABLE_NAME, data, connection=connection)
    return get_purchase(purchase_id, connection=connection)


def update_purchase(
    purchase_id: int,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one purchase by identifier and return the resulting row."""
    db_api.update(TABLE_NAME, data, {"id": purchase_id}, connection=connection)
    return get_purchase(purchase_id, connection=connection)


def rm_purchases(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove purchases matching all filters and return the affected row count.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting the purchases to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed purchases.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
