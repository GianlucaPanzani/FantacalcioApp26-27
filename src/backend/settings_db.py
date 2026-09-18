"""Database operations for the ``settings`` table."""

import sqlite3

from . import db_api


TABLE_NAME = "settings"


def get_setting(
    setting_id: int,
    proj: list[str] | None = None,
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return one setting by identifier, or ``None`` when it does not exist."""
    settings = get_settings({"id": setting_id}, proj=proj, connection=connection)
    return settings[0] if settings else None


def get_settings(
    filters: dict[str, db_api.SQLValue] | None = None,
    proj: list[str] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return settings matching all optional equality filters."""
    return db_api.get(TABLE_NAME, filters, proj, connection=connection)


def set_setting(
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Insert a setting from a column/value dictionary and return it."""
    setting_id = db_api.insert(TABLE_NAME, data, connection=connection)
    return get_setting(setting_id, connection=connection)


def update_setting(
    setting_id: int,
    data: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Update one setting by identifier and return the resulting row."""
    db_api.update(TABLE_NAME, data, {"id": setting_id}, connection=connection)
    return get_setting(setting_id, connection=connection)


def rm_settings(
    filters: dict[str, db_api.SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Remove settings matching all filters and return the affected row count.

    Params
    ----------
    filters : dict
        Required column/value conditions selecting the settings to remove.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.

    Returns
    -------
    int
        Number of removed settings.
    """
    return db_api.remove(TABLE_NAME, filters, connection=connection)
