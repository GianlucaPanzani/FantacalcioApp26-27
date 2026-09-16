"""SQLite storage primitives, independent of Streamlit and HTTP services.

Call ``create()`` once before using the database. All CRUD functions accept
``table, column, value``; a column can also be a list/tuple with matching values.
For reads/deletes these pairs are equality filters joined by AND. For
inserts/updates they are the fields to write. Updates additionally require a
nonempty ``where`` mapping, so the target rows are always explicit.

Each standalone write commits or rolls back in its own transaction. Pass the
connection yielded by ``transaction()`` to group several operations atomically.
Values are bound parameters; only known table/column names can enter SQL text.

This module enforces storage constraints, not application permissions or auction
rules such as sufficient budget, free roster slots or selecting the winning bid.
Those checks belong in the future services, inside the same write transaction.
"""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
import math
from pathlib import Path
import sqlite3


# Resolve the database relative to this module, regardless of the working folder.
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "db" / "fantacalcio.sqlite3"
SCHEMA_VERSION = 1
CONNECTION_TIMEOUT = 5.0

SQLValue = str | int | float | bytes | None
Columns = str | Sequence[str]
Values = SQLValue | Sequence[SQLValue]


# The schema is intentionally static. Changing existing tables will require an
# explicit migration; CREATE TABLE IF NOT EXISTS does not alter existing columns.
# STRICT tables require SQLite >= 3.37; built-in JSON support requires >= 3.38.
_TABLES = {
    # An account exists independently of its participation in individual auctions.
    # Optional OIDC identity uses both issuer and subject, never a display name.
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE
                CHECK (length(trim(username)) > 0 AND username = trim(username)),
            auth_issuer TEXT,
            auth_subject TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (auth_issuer, auth_subject),
            CHECK (
                (auth_issuer IS NULL AND auth_subject IS NULL)
                OR (auth_issuer IS NOT NULL AND auth_subject IS NOT NULL
                    AND length(trim(auth_issuer)) > 0
                    AND length(trim(auth_subject)) > 0)
            )
        ) STRICT
    """,
    # Official rules belong to the auction. Personal spending targets do not.
    # Defaults match the settings page; zero roster slots/budget are permitted.
    "auctions": """
        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            season TEXT NOT NULL CHECK (length(trim(season)) > 0),
            host_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            invite_code_hash TEXT NOT NULL UNIQUE
                CHECK (length(trim(invite_code_hash)) > 0),
            status TEXT NOT NULL DEFAULT 'lobby'
                CHECK (status IN ('lobby', 'running', 'completed')),
            total_budget INTEGER NOT NULL DEFAULT 500 CHECK (total_budget >= 0),
            goalkeeper_slots INTEGER NOT NULL DEFAULT 3 CHECK (goalkeeper_slots >= 0),
            defender_slots INTEGER NOT NULL DEFAULT 8 CHECK (defender_slots >= 0),
            midfielder_slots INTEGER NOT NULL DEFAULT 8 CHECK (midfielder_slots >= 0),
            forward_slots INTEGER NOT NULL DEFAULT 6 CHECK (forward_slots >= 0),
            defender_modifier_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (defender_modifier_enabled IN (0, 1)),
            midfielder_modifier_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (midfielder_modifier_enabled IN (0, 1)),
            player_switch_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (player_switch_enabled IN (0, 1)),
            points_goal_scored REAL NOT NULL DEFAULT 3 CHECK (points_goal_scored >= 0),
            points_goalkeeper_goal_conceded REAL NOT NULL DEFAULT -1
                CHECK (points_goalkeeper_goal_conceded <= 0),
            points_assist REAL NOT NULL DEFAULT 1 CHECK (points_assist >= 0),
            points_penalty_scored REAL NOT NULL DEFAULT 3 CHECK (points_penalty_scored >= 0),
            points_penalty_missed REAL NOT NULL DEFAULT -3 CHECK (points_penalty_missed <= 0),
            points_goalkeeper_penalty_conceded REAL NOT NULL DEFAULT -1
                CHECK (points_goalkeeper_penalty_conceded <= 0),
            points_goalkeeper_penalty_saved REAL NOT NULL DEFAULT 3
                CHECK (points_goalkeeper_penalty_saved >= 0),
            points_yellow_card REAL NOT NULL DEFAULT -0.5 CHECK (points_yellow_card <= 0),
            points_red_card REAL NOT NULL DEFAULT -1 CHECK (points_red_card <= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) STRICT
    """,
    # A user can join several auctions, but only once per auction. The host joins
    # through this same table; a separate host team is not necessary.
    "participants": """
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE RESTRICT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            team_name TEXT NOT NULL COLLATE NOCASE
                CHECK (length(trim(team_name)) > 0 AND team_name = trim(team_name)),
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (auction_id, user_id),
            UNIQUE (auction_id, team_name),
            UNIQUE (id, auction_id)
        ) STRICT
    """,
    # Each auction has a snapshot of its player catalog. source_id maps to CSV
    # Id/id; id is the internal DB identifier. Season comes from the parent auction.
    "players": """
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE RESTRICT,
            source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
            player TEXT NOT NULL CHECK (length(trim(player)) > 0),
            team TEXT NOT NULL DEFAULT '',
            fanta_role TEXT NOT NULL CHECK (fanta_role IN ('P', 'D', 'C', 'A')),
            mantra_role TEXT NOT NULL DEFAULT '',
            UNIQUE (auction_id, source_id),
            UNIQUE (id, auction_id)
        ) STRICT
    """,
    # The row with status='open' identifies the current player. A skipped player
    # may appear in a later lot; history is therefore not unique by player.
    "auction_lots": """
        CREATE TABLE IF NOT EXISTS auction_lots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL REFERENCES auctions(id) ON DELETE RESTRICT,
            player_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'sold', 'skipped')),
            version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
            opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT,
            FOREIGN KEY (player_id, auction_id)
                REFERENCES players(id, auction_id) ON DELETE RESTRICT,
            UNIQUE (id, auction_id),
            UNIQUE (id, auction_id, player_id)
        ) STRICT
    """,
    # Store the latest offer from each participant for each lot. Zero means no
    # active offer. Composite foreign keys prevent offers from a different auction.
    "bids": """
        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL,
            lot_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            amount INTEGER NOT NULL CHECK (amount >= 0),
            version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lot_id, auction_id)
                REFERENCES auction_lots(id, auction_id) ON DELETE RESTRICT,
            FOREIGN KEY (participant_id, auction_id)
                REFERENCES participants(id, auction_id) ON DELETE RESTRICT,
            UNIQUE (lot_id, participant_id)
        ) STRICT
    """,
    # Purchases are the source of truth for ownership, roster and spent budget.
    # A lot can produce one purchase; a player has one owner within an auction.
    "purchases": """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL,
            lot_id INTEGER NOT NULL UNIQUE,
            player_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            price INTEGER NOT NULL CHECK (price > 0),
            purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lot_id, auction_id, player_id)
                REFERENCES auction_lots(id, auction_id, player_id) ON DELETE RESTRICT,
            FOREIGN KEY (participant_id, auction_id)
                REFERENCES participants(id, auction_id) ON DELETE RESTRICT,
            UNIQUE (auction_id, player_id)
        ) STRICT
    """,
    # JSON preserves imported preference types (numbers, lists, booleans, null).
    # Only personal settings belong here; official rules remain in auctions.
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
            key TEXT NOT NULL CHECK (length(trim(key)) > 0),
            value_json TEXT NOT NULL CHECK (json_valid(value_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (participant_id, key)
        ) STRICT
    """,
    # Presence of a row represents a selected player. Imported CSV mln maps to
    # max_bid; these preferences never create an actual bid or purchase.
    "players_selected": """
        CREATE TABLE IF NOT EXISTS players_selected (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            max_bid INTEGER CHECK (max_bid >= 0),
            interest TEXT DEFAULT 'Da valutare',
            description TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (participant_id, auction_id)
                REFERENCES participants(id, auction_id) ON DELETE CASCADE,
            FOREIGN KEY (player_id, auction_id)
                REFERENCES players(id, auction_id) ON DELETE RESTRICT,
            UNIQUE (participant_id, player_id)
        ) STRICT
    """,
}

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS one_open_lot_per_auction "
    "ON auction_lots(auction_id) WHERE status = 'open'",
    "CREATE INDEX IF NOT EXISTS auctions_by_host ON auctions(host_user_id)",
    "CREATE INDEX IF NOT EXISTS participants_by_user ON participants(user_id)",
    "CREATE INDEX IF NOT EXISTS lots_by_player ON auction_lots(player_id, auction_id)",
    "CREATE INDEX IF NOT EXISTS bids_by_participant ON bids(participant_id, auction_id)",
    "CREATE INDEX IF NOT EXISTS purchases_by_participant "
    "ON purchases(participant_id, auction_id)",
    "CREATE INDEX IF NOT EXISTS preferences_by_player "
    "ON player_preferences(player_id, auction_id)",
)


def _connect(*, create_file: bool = False) -> sqlite3.Connection:
    """Open a connection owned by the caller; never share it across threads."""
    path = Path(DB_PATH).resolve()
    # SQLite reports a missing file in mode=rw; only create() may create it.
    connection = sqlite3.connect(
        path.as_uri() + ("?mode=rwc" if create_file else "?mode=rw"),
        uri=True,
        timeout=CONNECTION_TIMEOUT,
        isolation_level=None,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
    except BaseException:
        connection.close()
        raise
    return connection


def create_db() -> Path:
    """Create the database directory, nine static tables and indexes if absent.

    Return the absolute database path. Existing data is preserved and all schema
    statements run atomically. WAL permits readers during a write; SQLite still
    serializes writers, which wait up to CONNECTION_TIMEOUT seconds for the lock.
    No accounts, auction data or CSV imports are created automatically.

    SQLite 3.38+ is required for STRICT tables and built-in JSON validation.
    This function initializes schema version 1; it is not a migration runner.
    """
    path = Path(DB_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(create_file=True)) as connection:
        if connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
            raise RuntimeError("Could not enable SQLite WAL mode.")
        connection.execute("BEGIN IMMEDIATE")
        with connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise RuntimeError(f"Unsupported database schema version: {version}.")
            for statement in _TABLES.values():
                connection.execute(statement)
            for statement in _INDEXES:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return path


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Group operations into one write transaction with commit/rollback and close.

    Pass this connection to every CRUD call in the group. Let exceptions escape
    the block to roll back the entire group. BEGIN IMMEDIATE acquires the writer
    lock before reading/modifying state, so another writer cannot intervene.
    Keep the block short: do not wait for user input or make network calls here.

    Example::

        with transaction() as connection:
            user_id = insert("users", "username", "Mario", connection=connection)
            insert("participants", ["auction_id", "user_id", "team_name"],
                   [1, user_id, "Mario FC"], connection=connection)
    """
    with closing(_connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with connection:
            yield connection


@contextmanager
def _get_connection_scope(
    connection: sqlite3.Connection | None, *, write: bool = False
) -> Iterator[sqlite3.Connection]:
    """Reuse a connection from transaction(), or open and close one for this call."""
    if connection is not None:
        if not connection.in_transaction:
            raise ValueError("Pass an active connection from transaction().")
        yield connection
    elif write:
        with transaction() as owned_connection:
            yield owned_connection
    else:
        with closing(_connect()) as owned_connection:
            yield owned_connection


def _get_allowed_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    """Read valid column names for a table declared in this module."""
    if table not in _TABLES:
        raise ValueError(f"Unknown table: {table!r}.")
    return {row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _get_columns_values_pairs(column: Columns, value: Values, allowed_cols: set[str]) -> list[tuple[str, SQLValue]]:
    """Pair valid column names with values; SQLite checks supported value types."""
    if isinstance(column, str):
        columns, values = [column], [value]
    elif isinstance(column, (list, tuple)) and isinstance(value, (list, tuple)):
        columns, values = column, value
    else:
        raise ValueError("Use a column name and scalar, or matching lists/tuples.")

    # Avoid empty filters and silently dropping fields when zip() pairs the lists.
    if not columns or len(columns) != len(values):
        raise ValueError("Column and value sequences must have the same nonzero length.")
    if any(name not in allowed_cols for name in columns):
        raise ValueError("Unknown column name.")
    if len(set(columns)) != len(columns):
        raise ValueError("Column names must not be repeated.")

    # CSV imports may contain NaN; require an explicit None for missing values.
    for item in values:
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("NaN and infinite values are not supported; use None for SQL NULL.")
    return list(zip(columns, values))


def _build_predicates_condition(pairs: list[tuple[str, SQLValue]]) -> tuple[str, list[SQLValue]]:
    """Build equality filters, treating Python None as SQL NULL."""
    clauses, parameters = [], []
    for column, value in pairs:
        if value is None:
            clauses.append(f'"{column}" IS NULL')
        else:
            clauses.append(f'"{column}" = ?')
            parameters.append(value)
    return " AND ".join(clauses), parameters


def get(
    table: str, columns: Columns | None, values: Values, *,
    connection: sqlite3.Connection | None = None,
) -> list[dict[str, SQLValue]]:
    """Return matching rows as dictionaries ordered by id, or [] if none exist.

    ``get("users", "username", "Mario")`` filters by a single column.
    ``get("participants", ["auction_id", "user_id"], [1, 7])`` combines filters.
    ``get("users", None, None)`` explicitly reads every row; ``("auth_subject",
    None)`` instead matches rows whose auth_subject is SQL NULL.
    """
    with _get_connection_scope(connection) as conn_transaction:
        allowed_cols = _get_allowed_columns(conn_transaction, table)
        parameters = []
        query = f'SELECT * FROM "{table}"'
        if columns is None:
            if values is not None:
                raise ValueError("Reading all rows requires both column=None and value=None.")
        else:
            pairs = _get_columns_values_pairs(columns, values, allowed_cols)
            predicate, parameters = _build_predicates_condition(pairs)
            query += f" WHERE {predicate}"
        return [dict(row) for row in conn_transaction.execute(query + ' ORDER BY "id"', parameters)]


def insert(
    table: str, column: Columns, value: Values, *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Insert one row and return its id; omitted fields use schema defaults.

    Example: ``insert("users", ["username", "auth_issuer", "auth_subject"],
    ["Mario", "https://accounts.google.com", "provider-subject"])``.
    Duplicate keys, missing required fields and other constraint violations
    propagate as sqlite3.IntegrityError. Existing rows are never replaced.
    """
    with _get_connection_scope(connection, write=True) as conn_transaction:
        allowed_cols = _get_allowed_columns(conn_transaction, table)
        pairs = _get_columns_values_pairs(column, value, allowed_cols)
        columns = ", ".join(f'"{name}"' for name, _ in pairs)
        placeholders = ", ".join("?" for _ in pairs)
        cursor = conn_transaction.execute(
            f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
            [item for _, item in pairs],
        )
        return cursor.lastrowid


def update(
    table: str, column: Columns, value: Values, *,
    where: Mapping[str, SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Set fields on rows matching a required nonempty filter; return row count.

    Example: ``update("participants", "team_name", "New FC", where={"id": 7})``.
    All where entries are equality conditions joined by AND. Zero affected rows
    is a valid result. When present, updated_at is refreshed automatically unless
    explicitly supplied; version fields must be incremented by the service.
    Empty filters are rejected to prevent accidental table-wide updates.
    """
    if not where:
        raise ValueError("update() requires a nonempty where mapping.")
    with _get_connection_scope(connection, write=True) as conn_transaction:
        allowed_cols = _get_allowed_columns(conn_transaction, table)
        pairs = _get_columns_values_pairs(column, value, allowed_cols)
        filter_pairs = _get_columns_values_pairs(list(where), list(where.values()), allowed_cols)
        predicate, filters = _build_predicates_condition(filter_pairs)
        assignments = [f'"{name}" = ?' for name, _ in pairs]
        if "updated_at" in allowed_cols and "updated_at" not in dict(pairs):
            assignments.append('"updated_at" = CURRENT_TIMESTAMP')
        cursor = conn_transaction.execute(
            f'UPDATE "{table}" SET {", ".join(assignments)} WHERE {predicate}',
            [item for _, item in pairs] + filters,
        )
        return cursor.rowcount


def remove(
    table: str, column: Columns, value: Values, *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Delete matching rows and return their count; an explicit filter is required.

    Example: ``remove("bids", ["lot_id", "participant_id"], [3, 7])``.
    Passing None as a value matches SQL NULL, but column=None is never allowed.
    Referenced auction/account/history rows are protected by foreign keys;
    deleting an unreferenced participant also removes their personal preferences.
    """
    with _get_connection_scope(connection, write=True) as conn_transaction:
        allowed_cols = _get_allowed_columns(conn_transaction, table)
        pairs = _get_columns_values_pairs(column, value, allowed_cols)
        predicate, parameters = _build_predicates_condition(pairs)
        cursor = conn_transaction.execute(f'DELETE FROM "{table}" WHERE {predicate}', parameters)
        return cursor.rowcount


if __name__ == "__main__":
    # Needed for explicit initialization only: the import of this module does not create files.
    print(f"SQLite database ready: {create()}")
