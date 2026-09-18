"""Database operations for the ``users_auctions`` association table."""

import sqlite3

from . import db_api


TABLE_NAME = "users_auctions"


def get_user_auction(
    user_id: int,
    auction_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one user-auction association, or ``None`` if it does not exist.

    Params
    ----------
    user_id : int
        Identifier of the participating user.
    auction_id : int
        Identifier of the auction joined by the user.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict or None
        Association containing ``user_id`` and ``auction_id``, when present.
    """
    rows = db_api.get(
        TABLE_NAME,
        {"user_id": user_id, "auction_id": auction_id},
        connection=connection,
    )
    return rows[0] if rows else None


def set_user_auction(
    user_id: int,
    auction_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Associate one user with one auction and return the stored association.

    Params
    ----------
    user_id : int
        Identifier of the participating user.
    auction_id : int
        Identifier of the auction joined by the user.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    dict
        Inserted association containing ``user_id`` and ``auction_id``.
    """
    db_api.insert(
        TABLE_NAME,
        {"user_id": user_id, "auction_id": auction_id},
        connection=connection,
    )
    return get_user_auction(user_id, auction_id, connection=connection)
