# SQLite storage

`api.py` is the persistence layer. It uses Python's standard-library `sqlite3`
module and requires SQLite 3.38 or newer. It does not import Streamlit, start a
server, or run database operations when imported.

From the project root, initialize the database with:

```sh
python -m src.backend.api
```

This calls `create()` and creates `src/data/db/fantacalcio.sqlite3`. Calling it
again preserves the existing data. The location is resolved relative to `api.py`,
so changing the working directory does not change the database. Database files
and SQLite's `-wal`/`-shm` companion files are excluded from Git.

## Tables

All tables have an integer `id`. Foreign keys link these internal IDs; usernames,
team names and CSV IDs are not foreign keys.

| Table | Data and important relationships |
| --- | --- |
| `users` | Unique username; optional OIDC `auth_issuer` + `auth_subject`, unique as a pair. Neither passwords nor authentication sessions are implemented here. |
| `auctions` | Host user, season, invitation hash, status, official budget, role slots, three toggles and nine scoring values. Defaults match the settings page. |
| `participants` | User and team within an auction. A user joins once per auction; a team name is unique within that auction. The host also needs a participant row to bid. |
| `players` | Snapshot of the catalog for an auction, including name, team, classic role and Mantra role. `source_id` identifies the original CSV `Id`/`id`; season is inherited from the auction. |
| `auction_lots` | Each time a player is offered: `open`, `sold` or `skipped`. At most one open lot per auction identifies the current player. A skipped player can have a new lot later. |
| `bids` | Latest amount per participant and lot, unique for that pair. `0` represents no active offer. |
| `purchases` | Confirmed owner, player, lot and positive price. A player has one owner per auction; a lot can produce one purchase. |
| `participant_settings` | Personal settings imported for that participation: per-role spending targets, graphical options and filters. `key` stores the setting name; `value_json` preserves its type. |
| `player_preferences` | Shortlist rows for a participant: `max_bid`, `interest` and `description`. CSV `mln` maps to `max_bid`; a preference does not place a bid. |

Accounts and team names currently use SQLite `NOCASE` uniqueness, which ignores
ASCII letter case. Unicode normalization belongs in the future registration
service. Optional OIDC identity fields must either both be absent or both be
nonempty. Registration hashes the trimmed invitation code with SHA-256 before
looking it up. The auction creator must store the hash using the same convention;
the CRUD layer does not hash invitation codes automatically.

Each auction has its own catalog snapshot, so source IDs and roles are not mixed
between seasons. Import that catalog before preferences referring to its players.
Composite foreign keys keep lots, participants, bids, purchases and preferences
within the same auction. The lot's player must match the purchased player.

Rosters and ownership come from `purchases`. Remaining budget is
`auctions.total_budget - SUM(purchases.price)` for a participant. Remaining slots
are the corresponding official limit minus the count of purchased players with
that role. Missing purchases count as zero. These values are derived rather than
stored in additional mutable columns.

## CRUD contract

All four methods take `table`, `column`, `value`. `column` can be a string or a
list/tuple of column names; multiple columns require equally sized values.
Identifiers must refer to the declared schema, and values are SQL parameters.
No raw SQL predicates are accepted.

| Method | Meaning | Return value |
| --- | --- | --- |
| `get(table, column, value)` | Read rows matching all column/value pairs. `(table, None, None)` explicitly reads all rows. | List of dictionaries, ordered by `id`; `[]` if absent. |
| `insert(table, column, value)` | Insert one row; omitted fields use database defaults. | Inserted row's `id`. |
| `update(table, column, value, *, where)` | Set the supplied fields on rows matching the nonempty `where` dictionary. | Number of affected rows. |
| `remove(table, column, value)` | Delete rows matching all column/value pairs. An explicit filter is required. | Number of affected rows. |

`update()` needs the additional `where` argument to distinguish **what changes**
from **which rows change**. Both update and remove may affect multiple matching
rows; filter by `id` when targeting one row. Filtering a named column with `None`
uses SQL `IS NULL`. Empty update/delete filters are rejected.

```python
from src.backend import api  # Inside src/app.py, use: from backend import api

api.create()
user_id = api.insert("users", "username", "Mario")
rows = api.get("users", "id", user_id)
api.update("users", "username", "Mario92", where={"id": user_id})
api.remove("users", "id", user_id)

# Parallel columns/values allow inserts with several required fields.
user_id = api.insert(
    "users",
    ["username", "auth_issuer", "auth_subject"],
    ["Luigi", "https://accounts.google.com", "example-provider-subject"],
)
```

Values are Python strings, integers, finite floats, bytes, booleans or `None`.
SQLite stores booleans as `0`/`1`. Serialize personal settings using
`json.dumps(value)` and decode `value_json` with `json.loads()` after reading.
Invalid identifiers, empty filters, mismatched columns/values and nonfinite
floats raise `ValueError`. SQLite reports unsupported value types and schema
constraint failures (the latter as `sqlite3.IntegrityError`). Other incorrect
argument types can raise normal Python errors. Lock timeouts and other SQLite
failures propagate to the caller. Call `create()` before using the CRUD methods;
a missing database raises `sqlite3.OperationalError` without creating a file.

## Transactions and future services

Each standalone write owns a short transaction and closes its connection.
`transaction()` lets a service combine multiple calls into one commit:

```python
with api.transaction() as connection:
    user_id = api.insert("users", "username", "Guest", connection=connection)
    participant_id = api.insert(
        "participants",
        ["auction_id", "user_id", "team_name"],
        [existing_auction_id, user_id, "Guest FC"],
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

The next auction services must implement host permissions, allowed lot
transitions, tie handling, budget/slot checks and the complete purchase/undo
transaction. These rules are deliberately not inferred by generic CRUD calls.
The service must also freeze official rules/catalog roles once relevant to an
ongoing auction, and close the lot in the same transaction as confirming a
purchase. `version` fields on lots and bids are available for stale-write checks;
services must explicitly increment them. `updated_at`, when present, is refreshed
automatically by `update()` unless explicitly supplied.

Historical references use `ON DELETE RESTRICT`. For example, removing a user with
participations or a lot with bids raises an integrity error. Removing an otherwise
unreferenced participant also removes their personal settings and preferences.
Removing a purchase alone does not reopen its lot: undo behavior belongs in the
auction service.

The initial schema is version 1 (`PRAGMA user_version`). `create()` can initialize
it repeatedly, but does not migrate existing columns. Future schema changes need
an explicit migration. Account and participation lookups are connected to the
application entry point. Registration writes are implemented; CSV imports and
auction actions still need their service implementations.

## Identity lookup and Google login

`user_services.get_user(auth_issuer, auth_subject)` returns the matching account
dictionary or `None`. It never creates an account. The chosen username is separate
from the identity returned by Google.

`auction_services.get_partecipation(user_id, auction_id)` returns the matching
participation dictionary or `None`. The auction ID is required because a user can
belong to more than one auction. The entry point selects the user's membership
and derives host status from `auctions.host_user_id`.

`set_user(auth_issuer, auth_subject, username)` creates the account or updates the
username of that same identity. `set_partecipant(user_id, auction_id, team_name)`
creates the membership or updates its team name. Both return the saved row as a
dictionary. They each use a transaction, or reuse the optional `connection`
supplied by a caller. Identity claims must come from the verified `st.user`, not
from editable form inputs.

`register_to_auction(...)` checks the invitation and calls both setters in one
transaction, so a failed team save also rolls back account creation or renaming.
Auctions in `lobby` or `running` accept registrations; completed auctions do not.
The account is identified by provider and subject, never by a submitted username.
Repeated submissions reuse the same account and membership.

The registration page invokes this workflow from the form submit callback.
Text fields have widget keys, so the callback reads the values just submitted
from Session State. Database writes do not run on ordinary renders or when the
Google login button is clicked. The ZIP uploader is visible again, but its file
is not processed or persisted yet; the service's optional `zip_archive` argument
is reserved for that later implementation.

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
PYTHONDONTWRITEBYTECODE=1 python -m unittest src.tests.test_backend_api src.tests.test_identity_services src.tests.test_registration_page -v
```

Tests replace `api.DB_PATH` with a path inside a temporary directory. They check
CRUD behavior, persistence, constraints, rollback and concurrent registration
without modifying the application database. Streamlit AppTest also exercises the
form callback using a simulated Google identity; it does not contact Google.
