# SQLite storage

`db_api.py` is the persistence layer. It uses Python's standard-library `sqlite3`
module and requires SQLite 3.38 or newer. It does not import Streamlit, start a
server, or run database operations when imported.

From the project root, initialize the database with:

```sh
python -m src.backend.db_api
```

This calls `create_db()` and creates `src/data/db/fantacalcio.sqlite3`. Calling it
again preserves the existing data. The location is resolved relative to `db_api.py`,
so changing the working directory does not change the database. Database files
and SQLite's `-wal`/`-shm` companion files are excluded from Git.

Call `db_api.reset_db()` to delete the database and both companion files. It is
idempotent and does not recreate anything; call `db_api.create_db()` explicitly
afterwards when a clean database is required.

## Tables

All tables have an integer `id`. Foreign keys link these internal IDs; usernames,
team names and CSV IDs are not foreign keys.

| Table | Data and important relationships |
| --- | --- |
| `users` | Unique username and team name; optional OIDC `auth_issuer` + `auth_subject`, unique as a pair. Neither passwords nor authentication sessions are implemented here. |
| `auctions` | Host user, season, invitation hash, status, official budget, role slots, extraction modes, three toggles and nine scoring values. Defaults match the settings page. |
| `fanta_managers` | Associates one user with one auction. The team name remains in `users`. |
| `players` | Snapshot of the catalog for an auction, including name, team, classic role and Mantra role. `source_id` identifies the original CSV `Id`/`id`; season is inherited from the auction. |
| `purchases` | Final Fanta Manager, player and positive price. A player has one owner per auction; temporary offers are not persisted. |
| `settings` | Personal Fanta Manager settings: per-role spending targets, graphical options and filters. `key` stores the setting name; `value_json` preserves its type. |

Accounts and team names currently use SQLite `NOCASE` uniqueness, which ignores
ASCII letter case. Unicode normalization belongs in the future registration
service. Optional OIDC identity fields must either both be absent or both be
nonempty. Registration hashes the trimmed invitation code with SHA-256 before
looking it up. The auction creator must store the hash using the same convention;
the CRUD layer does not hash invitation codes automatically.

Each auction has its own catalog snapshot, so source IDs and roles are not mixed
between seasons. Import that catalog before purchase rows. Composite foreign keys
keep Fanta Managers and purchases within the same auction. Personal player
selections remain in one CSV per Fanta Manager.

Rosters and ownership come from `purchases`. Remaining budget is
`auctions.total_budget - SUM(purchases.price)` for a Fanta Manager. Remaining slots
are the corresponding official limit minus the count of purchased players with
that role. Missing purchases count as zero. These values are derived rather than
stored in additional mutable columns.

## CRUD and join contract

CRUD methods use dictionaries instead of parallel column/value arguments.
`data` contains fields to write, while `filters` contains equality conditions
joined by `AND`. Identifiers must refer to the declared schema, and values are
bound SQL parameters. No raw SQL predicates are accepted.

| Method | Meaning | Return value |
| --- | --- | --- |
| `get(table, filters=None)` | Read rows matching every filter. Omit filters to read all rows. | List of dictionaries, ordered by `id`; `[]` if absent. |
| `insert(table, data)` | Insert one row; omitted fields use database defaults. | Inserted row's `id`. |
| `update(table, data, filters)` | Set fields on rows matching the required filters. | Number of affected rows. |
| `remove(table, filters)` | Delete rows matching the required filters. | Number of affected rows. |
| `join(tables, filters, proj)` | Join an ordered foreign-key chain, filter it and project selected columns. | List of projected row dictionaries. |

`update()` separates **what changes** (`data`) from **which rows change**
(`filters`). Both update and remove may affect multiple matching
rows; filter by `id` when targeting one row. Filtering a named column with `None`
uses SQL `IS NULL`. Empty update/delete filters are rejected.

```python
from src.backend import db_api

db_api.create_db()
user_id = db_api.insert(
    "users",
    {"username": "Mario", "team_name": "Mario FC"},
)
rows = db_api.get("users", {"id": user_id})
db_api.update("users", {"username": "Mario92"}, {"id": user_id})
db_api.remove("users", {"id": user_id})

# One dictionary stores several fields without parallel lists.
user_id = db_api.insert(
    "users",
    {
        "username": "Luigi",
        "team_name": "Luigi FC",
        "auth_issuer": "https://accounts.google.com",
        "auth_subject": "example-provider-subject",
    },
)

# Tables form an explicit consecutive chain through declared foreign keys.
rows = db_api.join(
    ["users", "fanta_managers", "auctions"],
    {"auctions.id": 1},
    ["users.username", "users.team_name", "auctions.name"],
)
```

Each consecutive pair passed to `join()` must have exactly one direct foreign-key
relationship. A column name may be unqualified when it exists in only one table;
ambiguous names such as `id` must use `table.column`. Projected dictionaries keep
the names supplied in `proj` as their keys.

Values are Python strings, integers, finite floats, bytes, booleans or `None`.
SQLite stores booleans as `0`/`1`. Serialize personal settings using
`json.dumps(value)` and decode `value_json` with `json.loads()` after reading.
Invalid identifiers, empty mutation filters, malformed dictionaries and nonfinite
floats raise `ValueError`. SQLite reports unsupported value types and schema
constraint failures (the latter as `sqlite3.IntegrityError`). Other incorrect
argument types can raise normal Python errors. Lock timeouts and other SQLite
failures propagate to the caller. Call `create_db()` before using the CRUD methods;
a missing database raises `sqlite3.OperationalError` without creating a file.

## Transactions and future services

Each standalone write owns a short transaction and closes its connection.
`transaction()` lets a service combine multiple calls into one commit:

```python
with db_api.transaction() as connection:
    user_id = db_api.insert(
        "users",
        {"username": "Guest", "team_name": "Guest FC"},
        connection=connection,
    )
    fanta_manager_id = db_api.insert(
        "fanta_managers",
        {
            "auction_id": existing_auction_id,
            "user_id": user_id,
        },
        connection=connection,
    )
```

Every call in the block must receive `connection=connection`, including reads.
An exception escaping the block rolls back all its writes. Do not catch and
silence a failed operation inside the block if the whole action must roll back.
Connections must stay in the thread that opened them.

The connection uses foreign keys and a five-second lock timeout. WAL allows
readers alongside a writer; writes remain serialized. `BEGIN IMMEDIATE` obtains
the write lock before a service reads data it intends to change. Keep these
transactions short and perform network requests, ZIP parsing and user interaction
outside them.

The next auction services must implement host permissions, budget/slot checks and
the complete purchase/undo transaction. Temporary offers remain in Streamlit
state; only the final purchase is written to SQLite. These rules are deliberately
not inferred by generic CRUD calls. The service must also freeze official rules
and catalog roles once relevant to an ongoing auction. `updated_at`, when present,
is refreshed automatically by `update()` unless explicitly supplied.

Historical references use `ON DELETE RESTRICT`. For example, removing a user or
Fanta Manager linked to a purchase raises an integrity error. Removing an
otherwise unreferenced Fanta Manager also removes personal settings and selected
players. Purchase undo behavior belongs in the auction service.

The current schema is version 4 (`PRAGMA user_version`). `create_db()` can initialize
it repeatedly, but does not migrate existing columns. Future schema changes need
an explicit migration. Account and Fanta Manager lookups are connected to the
application entry point. Registration writes are implemented; CSV imports and
auction actions still need their service implementations.

## Table-specific modules and Google login

Each active table has a dedicated module: `users_db`, `auctions_db`,
`fanta_managers_db`, `players_db`, `purchases_db` and `settings_db`.
Every module exposes a singular getter by ID, a plural getter with optional filters,
a `set_*` insert accepting one data dictionary and an `update_*` accepting the row
ID plus a data dictionary.

Use `users_db.get_users({"auth_issuer": issuer, "auth_subject": subject})` to
look up an authenticated account. The chosen username and team name are separate
from the identity returned by Google.

`fanta_managers_db.register_to_auction(...)` locates users through their OIDC
identity and updates their username and team name when the account already exists.
It then inserts or reuses the association between that user and the auction.
Identity claims must come from the verified `st.user`, not editable form inputs.

`register_to_auction(...)` checks the invitation and performs all database writes
in one transaction, so a constraint failure also rolls back account creation or
renaming.
Auctions in `lobby` or `running` accept registrations; completed auctions do not.
The account is identified by provider and subject, never by a submitted username.
Repeated submissions reuse the same account and Fanta Manager record.

The registration page currently stores the authenticated user and team through
`users_db.set_user()`. The invitation flow can call `register_to_auction(...)`
when it is connected to the auction lobby. Text fields have widget keys, so the
callback reads the values just submitted from Session State. Database writes do
not run on ordinary renders or when the Google login button is clicked. The ZIP
uploader is visible, but its file is not processed or persisted yet; the
registration helper's optional `zip_archive` argument is reserved for that later
implementation.

The local `src/.streamlit/secrets.toml` is ignored by Git. A shareable template is
provided at `src/.streamlit/secrets.toml.example`. The local file has a generated
cookie secret; fill in `client_id` and `client_secret` from a Google OAuth **web
application** client. Register `http://localhost:8501/oauth2callback` as an
authorized redirect URI in that client. The `[auth.google]` section matches the
existing `st.login("google")` call.

Launch from the `src` directory so Streamlit finds this configuration and the
application's existing relative paths:

```sh
cd src
python -m streamlit run app.py
```

The login command also requires `Authlib>=1.3.2`. It is not currently installed
in the inspected environment; installation needs the owner's approval. For a
public ngrok URL, update both Google and `auth.redirect_uri` to use that origin
with the same `/oauth2callback` path.

Google login has not been tested end to end: client credentials and the Authlib
dependency are still missing. Registration also requires an existing auction
with a valid invitation hash. The initial host/auction creation flow remains to
be implemented; tests create fixtures in temporary databases.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest src.tests.test_backend_api src.tests.test_identity_services src.tests.test_table_db src.tests.test_registration_page -v
```

Tests replace `db_api.DB_PATH` with a path inside a temporary directory. They check
CRUD behavior, persistence, constraints, rollback and concurrent registration
without modifying the application database. Streamlit AppTest also exercises the
form callback using a simulated Google identity; it does not contact Google.
