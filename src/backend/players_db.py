"""Database operations for the ``players`` table."""

import sqlite3

from . import db_api


TABLE_NAME = "players"


def get_player(
    player_id: int,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one player by identifier, or ``None`` when it does not exist."""
    players = get_players({"id": player_id}, connection=connection)
    return players[0] if players else None


def get_players(
    filters: dict[str, db_api.SQLValue] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return players matching all optional equality filters."""
    return db_api.get(TABLE_NAME, filters, connection=connection)


def set_player(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert a player from a column/value dictionary and return it."""
    player_id = db_api.insert(TABLE_NAME, data, connection=connection)
    return get_player(player_id, connection=connection)


def update_player(
    player_id: int,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one player by identifier and return the resulting row."""
    db_api.update(TABLE_NAME, data, {"id": player_id}, connection=connection)
    return get_player(player_id, connection=connection)


def rm_players(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove players matching all filters and return the affected row count.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting the players to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed players.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
