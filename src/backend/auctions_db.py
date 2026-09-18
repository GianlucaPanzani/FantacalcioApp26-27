"""Database operations for the ``auctions`` table."""

import sqlite3

from . import db_api


TABLE_NAME = "auctions"


def get_auction(
    auction_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one auction by identifier, or ``None`` when it does not exist."""
    auctions = get_auctions({"id": auction_id}, connection=connection)
    return auctions[0] if auctions else None


def get_auctions(
    filters: dict[str, db_api.SQLValue] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return auctions matching all optional equality filters."""
    return db_api.get(TABLE_NAME, filters, connection=connection)


def set_auction(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert an auction from a column/value dictionary and return it."""
    auction_id = db_api.insert(TABLE_NAME, data, connection=connection)
    return get_auction(auction_id, connection=connection)


def update_auction(
    auction_id: int,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one auction by identifier and return the resulting row."""
    db_api.update(TABLE_NAME, data, {"id": auction_id}, connection=connection)
    return get_auction(auction_id, connection=connection)


def rm_auctions(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove auctions matching all filters and return the affected row count.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting the auctions to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed auctions.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
