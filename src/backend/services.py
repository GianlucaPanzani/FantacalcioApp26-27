
import hashlib

from backend import db_api
from lib.data_handler import parse_guest_archive, store_guest_archive
from .auctions_db import get_auctions, set_auction
from .users_db import get_user, get_users, set_user, update_user
from .users_auctions_db import get_user_auction, set_user_auction


def register_user(
    user_data: dict[str, str],
    zip_archive: bytes | None = None,
) -> dict:
    """Register an authenticated user.

    Params
    ----------
    user_data : dict of str
        Verified identity, username and team name of the registering user.
    zip_archive : bytes or None
        Optional personal backup containing settings and selected players.

    Returns
    -------
    dict
        Existing or newly inserted user row associated with the auction.
    """

    account_data = {
        "auth_issuer": user_data["auth_issuer"],
        "auth_subject": user_data["auth_subject"],
        "username": user_data["username"].strip(),
        "team_name": user_data["team_name"].strip(),
        "current_auction_id": None
    }
    if not account_data["username"]:
        raise ValueError("Enter a username.")
    if not account_data["team_name"]:
        raise ValueError("Enter a team name.")

    if zip_archive is not None:
        parse_guest_archive(zip_archive)

    with db_api.transaction() as connection:

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

        # Handle archive zip file
        if zip_archive is not None:
            store_guest_archive(
                zip_archive,
                user["id"],
                account_data["username"],
                connection=connection,
            )

        return user


def register_to_auction(user_id: int, auction_code: str):
    """Associate an existing user with the auction identified by its code.

    Params
    ----------
    user_id : int
        Identifier of the registered user.
    auction_code : str
        Plain six-character code identifying the auction.

    Returns
    -------
    dict
        Updated user with the selected auction identifier.
    """
    auction_code = auction_code.strip()
    if not auction_code:
        raise ValueError("Enter the auction code.")
    code_hash = hashlib.sha256(auction_code.encode("utf-8")).hexdigest()
    with db_api.transaction() as connection:
        auctions = get_auctions(
            filters={"auction_code_hash": code_hash},
            connection=connection,
        )
        if not auctions or auctions[0]["status"] == "completed":
            raise ValueError("Invalid invitation or auction no longer open.")
        auction_id = auctions[0]["id"]

        user = update_user(
            user_id=user_id,
            data={"current_auction_id": auction_id},
            connection=connection,
        )
        if get_user_auction(user_id, auction_id, connection=connection) is None:
            set_user_auction(
                user_id=user_id,
                auction_id=auction_id,
                connection=connection,
            )
        return user


def create_auction(user_id: int, auction_code_hash: str | None):
    if auction_code_hash is None:
        return

    # Check if the user exists
    user = get_user(
        user_id=user_id,
        proj=["id"]
    )
    if user is None:
        raise Exception(f"User ID {user_id} doesn't exist.")
    
    # Create the auction associated to that user
    auction_data = {}
    # TODO: create data to be inserted in the auctions table
    auction = set_auction(data=auction_data)
    set_user_auction(
        user_id=user_id,
        auction_id=auction["id"]
    )
    return