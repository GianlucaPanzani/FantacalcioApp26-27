
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import pandas as pd
import tempfile

from backend import db_api
from lib.data_handler import parse_guest_archive
from .auctions_db import get_auctions
from .users_db import get_users, set_user, update_user
from .fanta_managers_db import get_fanta_managers, set_fanta_manager
from .settings_db import rm_settings, set_setting




def _store_selected_players_csv(username: str, df: pd.DataFrame) -> str:
    """Atomically store one Fanta Manager's validated selection CSV.

    Params
    ----------
    username : str
        Username used to identify the personal selection file.
    content : bytes
        Validated CSV content extracted from the personal backup.

    Returns
    -------
    str
        Selection CSV path relative to the ``src`` directory.
    """

    selection_dir = Path(__file__).resolve().parents[1] / "data/csv/pages/selection"
    selection_dir.mkdir(parents=True, exist_ok=True)
    selection_path = selection_dir / f"selection_selected_players_{username}.csv"
    
    df.to_csv(selection_path)

    src_directory = Path(__file__).resolve().parents[1]
    try:
        return selection_path.relative_to(src_directory).as_posix()
    except ValueError:
        return selection_path.as_posix()


def register_to_auction(
    user_data: dict[str, str],
    invite_code: str,
    zip_archive: bytes | None = None,
) -> dict:
    """Register an authenticated user as a Fanta Manager in an auction.

    Params
    ----------
    user_data : dict of str
        Verified identity, username and team name of the registering user.
    invite_code : str
        Plain invitation code used to locate the auction.
    zip_archive : bytes or None
        Optional personal backup containing settings and selected players.

    Returns
    -------
    dict
        Existing or newly inserted Fanta Manager row.
    """

    account_data = {
        "auth_issuer": user_data["auth_issuer"],
        "auth_subject": user_data["auth_subject"],
        "username": user_data["username"].strip(),
        "team_name": user_data["team_name"].strip(),
    }
    if not account_data["username"]:
        raise ValueError("Enter a username.")
    if not account_data["team_name"]:
        raise ValueError("Enter a team name.")
    invite_code = invite_code.strip()
    if not invite_code:
        raise ValueError("Enter the auction invitation code.")

    backup = parse_guest_archive(zip_archive) if zip_archive is not None else None

    invite_hash = hashlib.sha256(invite_code.encode("utf-8")).hexdigest()
    with db_api.transaction() as connection:
        auctions = get_auctions(
            {"invite_code_hash": invite_hash},
            connection=connection,
        )
        if not auctions or auctions[0]["status"] == "completed":
            raise ValueError("Invalid invitation or auction no longer open.")

        # Get the user if exists
        users = get_users(
            filters={
                "auth_issuer": account_data["auth_issuer"],
                "auth_subject": account_data["auth_subject"],
            },
            connection=connection,
        )

        # Update if user exists or set if not
        if users:
            user = update_user(
                user_id=users[0]["id"],
                data=account_data,
                connection=connection,
            )
        else:
            user = set_user(
                data=account_data,
                connection=connection,
            )

        # Get the associated fanta manager
        fanta_managers = get_fanta_managers(
            filters={
                "user_id": user["id"],
                "auction_id": auctions[0]["id"],
            },
            connection=connection,
        )
        # Case of existing fanta manager
        if fanta_managers:
            fanta_manager = fanta_managers[0]
        # Case of fanta manager to be created
        else:
            fanta_manager = set_fanta_manager(
                data={
                    "user_id": user["id"],
                    "auction_id": auctions[0]["id"],
                },
                connection=connection,
            )

        # Handle archive zip file
        if backup is not None:
            rm_settings(
                {"fanta_manager_id": fanta_manager["id"]},
                connection=connection,
            )

            for key, value in backup["settings"].items():
                set_setting(
                    data={
                        "fanta_manager_id": fanta_manager["id"],
                        "key": key,
                        "value_json": json.dumps(value, ensure_ascii=False),
                    },
                    connection=connection,
                )

            selection_csv_path = _store_selected_players_csv(
                account_data["username"],
                pd.read_csv(BytesIO(backup["selection_csv"])),
            )
            set_setting(
                data={
                    "fanta_manager_id": fanta_manager["id"],
                    "key": "selection_selected_players_csv_path_key",
                    "value_json": json.dumps(selection_csv_path),
                },
                connection=connection,
            )

        return fanta_manager
