"""Delete rows selected by explicit equality filters.

Edit ``TABLE`` and ``FILTERS`` below before running the script.  The filters
are combined with ``AND`` by ``db_api.remove``.

Run from the project root with::

    python src/scripts/delete_query.py
"""

import sys
from pathlib import Path


# Make the ``src`` package importable when this file is run directly.
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backend import db_api


# ---------------------------------------------------------------------------
# Edit these values for the row that must be deleted.
TABLE = "users"
FILTERS = {"id": 3}


def main() -> None:
    """Delete rows matching ``TABLE`` and ``FILTERS`` and print the result."""
    if not FILTERS:
        raise ValueError("FILTERS must contain at least one condition.")

    with db_api.transaction() as connection:
        deleted_rows = db_api.remove(
            table=TABLE,
            filters=FILTERS,
            connection=connection,
        )

    print(f"Deleted {deleted_rows} row(s) from '{TABLE}'.")


if __name__ == "__main__":
    main()
