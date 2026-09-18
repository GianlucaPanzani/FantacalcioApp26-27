"""SQLite storage primitives, independent of Streamlit and HTTP services.

Call ``create_db()`` once before using the database. CRUD functions accept
dictionaries: ``data`` contains fields to write and ``filters`` contains equality
conditions joined by AND. Updates and deletes require nonempty filters, so their
target rows are always explicit.

Each standalone write commits or rolls back in its own transaction. Pass the
connection yielded by ``transaction()`` to group several operations atomically.
Values are bound parameters; only known table/column names can enter SQL text.

This module enforces storage constraints, not application permissions or auction
rules such as sufficient budget or free roster slots. Those checks belong in the
services, inside the same write transaction.
"""

from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
import math
from pathlib import Path
import sqlite3


# Resolve the database relative to this module, regardless of the working folder.
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "db" / "fantacalcio.sqlite3"
SCHEMA_VERSION = 5
CONNECTION_TIMEOUT = 5.0

SQLValue = str | int | float | bytes | None


# The schema is intentionally static. Changing existing tables will require an
# explicit migration; CREATE TABLE IF NOT EXISTS does not alter existing columns.
# STRICT tables require SQLite >= 3.37; built-in JSON support requires >= 3.38.
_TABLES = {
    # A user is also the Fanta Manager participating in one auction. The auction
    # is nullable while the host account is being created before its auction.
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER REFERENCES auctions(id) ON DELETE RESTRICT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE
                CHECK (length(trim(username)) > 0 AND username = trim(username)),
            team_name TEXT NOT NULL COLLATE NOCASE UNIQUE
                CHECK (length(trim(team_name)) > 0 AND team_name = trim(team_name)),
            auth_issuer TEXT,
            auth_subject TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (auth_issuer, auth_subject),
            UNIQUE (id, auction_id),
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
            player_extraction_order TEXT NOT NULL DEFAULT 'random'
                CHECK (player_extraction_order IN ('random', 'alphabetic_order')),
            player_extraction_scope TEXT NOT NULL DEFAULT 'on_all_players'
                CHECK (player_extraction_scope IN ('by_role', 'on_all_players')),
            role_extraction_order TEXT NOT NULL DEFAULT 'in_order_P_D_C_A'
                CHECK (role_extraction_order IN ('in_order_P_D_C_A', 'random')),
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
    # Purchases are the source of truth for ownership, roster and spent budget.
    # Only the final assignment is persisted; temporary offers stay in app state.
    "purchases": """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auction_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            price INTEGER NOT NULL CHECK (price > 0),
            purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id, auction_id)
                REFERENCES players(id, auction_id) ON DELETE RESTRICT,
            FOREIGN KEY (user_id, auction_id)
                REFERENCES users(id, auction_id) ON DELETE RESTRICT,
            UNIQUE (auction_id, player_id)
        ) STRICT
    """,
    # JSON preserves imported preference types (numbers, lists, booleans, null).
    # Only personal settings belong here; official rules remain in auctions.
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL CHECK (length(trim(key)) > 0),
            value_json TEXT NOT NULL CHECK (json_valid(value_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, key)
        ) STRICT
    """,
}

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS auctions_by_host ON auctions(host_user_id)",
    "CREATE INDEX IF NOT EXISTS users_by_auction ON users(auction_id)",
    "CREATE INDEX IF NOT EXISTS purchases_by_user "
    "ON purchases(user_id, auction_id)",
)


def _connect(create_file: bool = False) -> sqlite3.Connection:
    """Open a database connection owned by the caller.

    Params
    ----------
    create_file : bool
        Whether SQLite may create the database when it does not exist.

    Returns
    -------
    sqlite3.Connection
        Configured connection with row dictionaries and foreign keys enabled.
    """
    path = Path(DB_PATH).resolve()
    # SQLite reports a missing file in mode=rw; only create_db() may create it.
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
    """Create the database directory, five static tables and indexes if absent.

    Return the absolute database path. Existing data is preserved and all schema
    statements run atomically. WAL permits readers during a write; SQLite still
    serializes writers, which wait up to CONNECTION_TIMEOUT seconds for the lock.
    No accounts, auction data or CSV imports are created automatically.

    SQLite 3.38+ is required for STRICT tables and built-in JSON validation.
    This function initializes schema version 5; it is not a migration runner.

    Returns
    -------
    pathlib.Path
        Absolute path of the initialized database file.
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


def reset_db() -> None:
    """Delete the SQLite database and its WAL companion files if they exist.

    Call ``create_db()`` afterwards when a new database using the current schema
    is required. The function is idempotent and does not recreate any data.
    """
    path = Path(DB_PATH).resolve()
    for database_file in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        database_file.unlink(missing_ok=True)


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Group operations into one write transaction with commit/rollback and close.

    Pass this connection to every CRUD call in the group. Let exceptions escape
    the block to roll back the entire group. BEGIN IMMEDIATE acquires the writer
    lock before reading/modifying state, so another writer cannot intervene.
    Keep the block short: do not wait for user input or make network calls here.

    Example::

        with transaction() as connection:
            user_id = insert(
                "users",
                {"username": "Mario", "team_name": "Mario FC"},
                connection=connection,
            )
            update(
                "users", {"auction_id": 1}, {"id": user_id},
                connection=connection,
            )

    Yields
    ------
    sqlite3.Connection
        Active connection that commits on success and rolls back on error.
    """
    with closing(_connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with connection:
            yield connection


@contextmanager
def _get_connection_scope(
    connection: sqlite3.Connection | None, write: bool = False
) -> Iterator[sqlite3.Connection]:
    """Provide an active connection for one database operation.

    Params
    ----------
    connection : sqlite3.Connection or None
        Existing active transaction connection to reuse.
    write : bool
        Whether a missing connection should open a write transaction.

    Yields
    ------
    sqlite3.Connection
        Reused or locally owned connection.
    """
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
    """Read valid columns for a table declared by this module.

    Params
    ----------
    connection : sqlite3.Connection
        Open database connection used to inspect the table.
    table : str
        Declared table name.

    Returns
    -------
    set of str
        Column names accepted by the CRUD helpers.
    """
    if table not in _TABLES:
        raise ValueError(f"Unknown table: {table!r}.")
    return {row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _get_data_pairs(
    data: Mapping[str, SQLValue],
    allowed_columns: set[str],
    allow_empty: bool = False,
) -> list[tuple[str, SQLValue]]:
    """Validate a data or filter mapping and return its ordered pairs.

    Params
    ----------
    data : mapping
        Column names mapped to values.
    allowed_columns : set of str
        Valid columns for the target table.
    allow_empty : bool
        Whether an empty mapping is valid.

    Returns
    -------
    list of tuple
        Validated ``(column, value)`` pairs.
    """
    if not isinstance(data, Mapping):
        raise ValueError("Use a dictionary that maps column names to values.")
    if not data and not allow_empty:
        raise ValueError("The data or filter dictionary must not be empty.")
    if any(name not in allowed_columns for name in data):
        raise ValueError("Unknown column name.")

    # CSV imports may contain NaN; require an explicit None for missing values.
    for value in data.values():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("NaN and infinite values are not supported; use None for SQL NULL.")
    return list(data.items())


def _build_predicates_condition(pairs: list[tuple[str, SQLValue]]) -> tuple[str, list[SQLValue]]:
    """Build equality predicates, treating Python ``None`` as SQL NULL.

    Params
    ----------
    pairs : list of tuple
        Validated column/value filters.

    Returns
    -------
    tuple of str and list
        SQL condition and bound non-null parameter values.
    """
    clauses, parameters = [], []
    for column, value in pairs:
        if value is None:
            clauses.append(f'"{column}" IS NULL')
        else:
            clauses.append(f'"{column}" = ?')
            parameters.append(value)
    return " AND ".join(clauses), parameters



def _get_join_condition(
    connection: sqlite3.Connection,
    left_table: str,
    right_table: str,
) -> str:
    """Return the foreign-key condition between two consecutive tables.

    Params
    ----------
    connection : sqlite3.Connection
        Open database connection used to inspect foreign keys.
    left_table : str
        Table already present in the join chain.
    right_table : str
        Next table to join.

    Returns
    -------
    str
        SQL equality condition for the single relationship between the tables.
    """
    relationships = []
    for child_table, parent_table in (
        (left_table, right_table),
        (right_table, left_table),
    ):
        foreign_keys = {}
        for row in connection.execute(
            f'PRAGMA foreign_key_list("{child_table}")'
        ):
            if row["table"] == parent_table:
                foreign_keys.setdefault(row["id"], []).append(row)

        for rows in foreign_keys.values():
            conditions = []
            for row in sorted(rows, key=lambda item: item["seq"]):
                conditions.append(
                    f'"{child_table}"."{row["from"]}" = '
                    f'"{parent_table}"."{row["to"]}"'
                )
            relationships.append(" AND ".join(conditions))

    if not relationships:
        raise ValueError(
            f"Tables {left_table!r} and {right_table!r} have no direct "
            "foreign-key relationship."
        )
    if len(relationships) > 1:
        raise ValueError(
            f"Tables {left_table!r} and {right_table!r} have more than one "
            "foreign-key relationship."
        )
    return relationships[0]


def _resolve_join_column(
    column: str,
    tables: list[str],
    allowed_columns: dict[str, set[str]],
) -> str:
    """Validate a join column and return its qualified SQL identifier.

    Params
    ----------
    column : str
        Plain or ``table.column`` identifier.
    tables : list of str
        Tables included in the join.
    allowed_columns : dict
        Valid columns indexed by table.

    Returns
    -------
    str
        Safely quoted and table-qualified SQL identifier.
    """
    if not isinstance(column, str) or not column:
        raise ValueError("Join columns must be nonempty strings.")

    parts = column.split(".")
    if len(parts) == 2:
        table, column_name = parts
        if table not in tables or column_name not in allowed_columns.get(table, set()):
            raise ValueError(f"Unknown join column: {column!r}.")
        return f'"{table}"."{column_name}"'
    if len(parts) != 1:
        raise ValueError(f"Invalid join column: {column!r}.")

    matching_tables = [
        table for table in tables if column in allowed_columns[table]
    ]
    if not matching_tables:
        raise ValueError(f"Unknown join column: {column!r}.")
    if len(matching_tables) > 1:
        raise ValueError(
            f"Ambiguous join column {column!r}; qualify it as 'table.column'."
        )
    return f'"{matching_tables[0]}"."{column}"'


def get(
    table: str,
    filters: dict[str, SQLValue] | None = None,
    proj: list[str] | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict[str, SQLValue]]:
    """Return matching rows as dictionaries ordered by id, or [] if none exist.

    ``get("users", {"username": "Mario"}, ["id", "username"])`` filters by
    one column and returns only the requested fields.
    Multiple entries are combined with AND. Omitting ``filters`` reads every row;
    ``{"auth_subject": None}`` instead matches SQL NULL. Omitting ``proj``
    returns every column.

    Params
    ----------
    table : str
        Declared table to read.
    filters : dict or None
        Equality conditions, or ``None``/an empty dictionary to read all rows.
    proj : list of str or None
        Columns to return, or ``None`` to return every table column.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    list of dict
        Matching rows ordered by identifier.
    """
    with _get_connection_scope(connection) as conn_transaction:
        allowed_columns = _get_allowed_columns(conn_transaction, table)
        if proj is None:
            projection = "*"
        else:
            if not isinstance(proj, list) or not proj:
                raise ValueError("proj must be a nonempty list of column names.")
            if any(
                not isinstance(column, str) or column not in allowed_columns
                for column in proj
            ):
                raise ValueError("Unknown projection column name.")
            projection = ", ".join(f'"{column}"' for column in proj)

        filter_pairs = _get_data_pairs(
            {} if filters is None else filters,
            allowed_columns,
            allow_empty=True,
        )
        parameters = []
        query = f'SELECT {projection} FROM "{table}"'
        if filter_pairs:
            predicate, parameters = _build_predicates_condition(filter_pairs)
            query += f" WHERE {predicate}"
        return [dict(row) for row in conn_transaction.execute(query + ' ORDER BY "id"', parameters)]


def insert(
    table: str,
    data: dict[str, SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Insert one row and return its id; omitted fields use schema defaults.

    Example: ``insert("users", {"username": "Mario", "team_name": "Mario FC",
    "auth_issuer": "https://accounts.google.com",
    "auth_subject": "provider-subject"})``.
    Duplicate keys, missing required fields and other constraint violations
    propagate as sqlite3.IntegrityError. Existing rows are never replaced.

    Params
    ----------
    table : str
        Declared table to insert into.
    data : dict
        Columns and values to store.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    int
        Identifier of the inserted row.
    """
    with _get_connection_scope(connection, write=True) as conn_transaction:
        allowed_columns = _get_allowed_columns(conn_transaction, table)
        pairs = _get_data_pairs(data, allowed_columns)
        columns = ", ".join(f'"{name}"' for name, _ in pairs)
        placeholders = ", ".join("?" for _ in pairs)
        cursor = conn_transaction.execute(
            f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
            [item for _, item in pairs],
        )
        return cursor.lastrowid


def update(
    table: str,
    data: dict[str, SQLValue],
    filters: dict[str, SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Set fields on rows matching a required nonempty filter; return row count.

    Example: ``update("users", {"auction_id": 9}, {"id": 7})``.
    All filter entries are equality conditions joined by AND. Zero affected rows
    is a valid result. When present, updated_at is refreshed automatically unless
    explicitly supplied; version fields must be incremented by the service.
    Empty filters are rejected to prevent accidental table-wide updates.

    Params
    ----------
    table : str
        Declared table to update.
    data : dict
        Columns and new values to store.
    filters : dict
        Required equality filters that select target rows.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    int
        Number of updated rows.
    """
    with _get_connection_scope(connection, write=True) as conn_transaction:
        allowed_columns = _get_allowed_columns(conn_transaction, table)
        pairs = _get_data_pairs(data, allowed_columns)
        filter_pairs = _get_data_pairs(filters, allowed_columns)
        predicate, filter_values = _build_predicates_condition(filter_pairs)
        assignments = [f'"{name}" = ?' for name, _ in pairs]
        if "updated_at" in allowed_columns and "updated_at" not in data:
            assignments.append('"updated_at" = CURRENT_TIMESTAMP')
        cursor = conn_transaction.execute(
            f'UPDATE "{table}" SET {", ".join(assignments)} WHERE {predicate}',
            [item for _, item in pairs] + filter_values,
        )
        return cursor.rowcount


def remove(
    table: str,
    filters: dict[str, SQLValue],
    connection: sqlite3.Connection | None = None,
) -> int:
    """Delete matching rows and return their count; an explicit filter is required.

    Example: ``remove("settings", {"user_id": 3, "key": "theme"})``.
    Passing None as a value matches SQL NULL, but an empty filter is not allowed.
    Referenced auction/account/history rows are protected by foreign keys;
    deleting an unreferenced user also removes personal settings.

    Params
    ----------
    table : str
        Declared table to delete from.
    filters : dict
        Required equality filters that select rows to delete.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    int
        Number of deleted rows.
    """
    with _get_connection_scope(connection, write=True) as conn_transaction:
        allowed_columns = _get_allowed_columns(conn_transaction, table)
        pairs = _get_data_pairs(filters, allowed_columns)
        predicate, parameters = _build_predicates_condition(pairs)
        cursor = conn_transaction.execute(f'DELETE FROM "{table}" WHERE {predicate}', parameters)
        return cursor.rowcount


def join(
    tables: list[str],
    filters: dict[str, SQLValue] | None,
    proj: list[str],
    connection: sqlite3.Connection | None = None,
) -> list[dict[str, SQLValue]]:
    """Join consecutive related tables and return the projected filtered rows.

    Each consecutive pair in ``tables`` must have exactly one direct foreign-key
    relationship. Plain column names are accepted only when they occur in one of
    the joined tables; qualify ambiguous names as ``table.column``. Result keys
    preserve the identifiers supplied in ``proj``.

    Params
    ----------
    tables : list of str
        Ordered join chain containing at least two distinct declared tables.
    filters : dict or None
        Equality conditions keyed by plain or qualified column names.
    proj : list of str
        Plain or qualified columns to include in each result.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    list of dict
        Projected matching rows, ordered by the first table's identifier.
    """
    if not isinstance(tables, list) or len(tables) < 2:
        raise ValueError("join() requires a list containing at least two tables.")
    if any(not isinstance(table, str) for table in tables):
        raise ValueError("join() table names must be strings.")
    if len(set(tables)) != len(tables):
        raise ValueError("join() table names must not be repeated.")
    if not isinstance(proj, list) or not proj:
        raise ValueError("join() requires a nonempty projection list.")
    if any(not isinstance(column, str) for column in proj):
        raise ValueError("Projected column names must be strings.")
    if len(set(proj)) != len(proj):
        raise ValueError("Projected columns must not be repeated.")
    if filters is not None and not isinstance(filters, Mapping):
        raise ValueError("Use a filter dictionary that maps columns to values.")

    with _get_connection_scope(connection) as conn_transaction:
        allowed_columns = {
            table: _get_allowed_columns(conn_transaction, table)
            for table in tables
        }
        projections = [
            (_resolve_join_column(column, tables, allowed_columns), column)
            for column in proj
        ]
        query = "SELECT " + ", ".join(
            f'{column_sql} AS "{result_key}"'
            for column_sql, result_key in projections
        )
        query += f' FROM "{tables[0]}"'

        for left_table, right_table in zip(tables, tables[1:]):
            condition = _get_join_condition(
                conn_transaction,
                left_table,
                right_table,
            )
            query += f' JOIN "{right_table}" ON {condition}'

        parameters = []
        filter_clauses = []
        for column, value in (filters or {}).items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(
                    "NaN and infinite values are not supported; use None for SQL NULL."
                )
            column_sql = _resolve_join_column(column, tables, allowed_columns)
            if value is None:
                filter_clauses.append(f"{column_sql} IS NULL")
            else:
                filter_clauses.append(f"{column_sql} = ?")
                parameters.append(value)

        if filter_clauses:
            query += " WHERE " + " AND ".join(filter_clauses)
        query += f' ORDER BY "{tables[0]}"."id"'

        return [
            dict(row)
            for row in conn_transaction.execute(query, parameters)
        ]


if __name__ == "__main__":
    # Needed for explicit initialization only: the import of this module does not create files.
    print(f"SQLite database ready: {create_db()}")
