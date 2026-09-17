

from contextlib import nullcontext
import hashlib
import sqlite3

from . import api
from .user_services import set_user


def get_fanta_manager(
    user_id: int, auction_id: int, connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return the user's Fanta Manager record for an auction.

    Params
    ----------
    user_id : int
        Identifier of the registered user.
    auction_id : int
        Identifier of the auction to search.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    dict or None
        Matching Fanta Manager row, or ``None`` when the user has not joined.
    """
    # Scope the lookup to one auction, since a user can join several auctions.
    fanta_managers = api.get(
        table="fanta_managers",
        filters={"user_id": user_id, "auction_id": auction_id},
        connection=connection,
    )
    return fanta_managers[0] if fanta_managers else None


def get_fanta_managers(
    auction_id: int, connection: sqlite3.Connection | None = None,
) -> list[dict]:
    """Return all Fanta Managers registered for an auction.

    Params
    ----------
    auction_id : int
        Identifier of the auction to search.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    list of dict
        Fanta Manager rows ordered by their database identifier.
    """
    return api.get(
        table="fanta_managers",
        filters={"auction_id": auction_id},
        connection=connection,
    )


def set_fanta_manager(
    user_id: int, auction_id: int, team_name: str,
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Create or rename the team managed by a user in an auction.

    Params
    ----------
    user_id : int
        Identifier of the registered user.
    auction_id : int
        Identifier of the auction the user manages a team in.
    team_name : str
        Team name to create or assign.
    connection : sqlite3.Connection or None
        Active transaction connection to reuse, when provided.

    Returns
    -------
    dict
        Newly created or updated Fanta Manager row.
    """
    # Keep one Fanta Manager per user and auction; the database checks duplicates.
    team_name = team_name.strip()
    if not team_name:
        raise ValueError("Enter a team name.")

    context = api.transaction() if connection is None else nullcontext(connection)
    with context as conn:
        fanta_manager = get_fanta_manager(user_id, auction_id, connection=conn)
        if fanta_manager is None:
            api.insert(
                "fanta_managers",
                {
                    "user_id": user_id,
                    "auction_id": auction_id,
                    "team_name": team_name,
                },
                connection=conn,
            )
        else:
            api.update(
                "fanta_managers",
                {"team_name": team_name},
                {"id": fanta_manager["id"]},
                connection=conn,
            )

        return get_fanta_manager(user_id, auction_id, connection=conn)


def register_to_auction(
    auth_issuer: str, auth_subject: str, username: str,
    invite_code: str, team_name: str, zip_archive: bytes | None = None,
) -> dict:
    """Register an authenticated user as a Fanta Manager in an auction.

    Params
    ----------
    auth_issuer : str
        OIDC provider that authenticated the user.
    auth_subject : str
        Stable user identifier supplied by the OIDC provider.
    username : str
        Application username chosen by the user.
    invite_code : str
        Plain invitation code used to locate the auction.
    team_name : str
        Team name managed by the user in the auction.
    zip_archive : bytes or None
        Reserved personal backup; importing it is not implemented yet.

    Returns
    -------
    dict
        Created or existing Fanta Manager row.
    """

    # Match the invitation to an auction that still accepts registrations.
    invite_hash = hashlib.sha256(invite_code.strip().encode("utf-8")).hexdigest()
    with api.transaction() as conn:
        auctions = api.get(
            "auctions",
            {"invite_code_hash": invite_hash},
            connection=conn,
        )
        if not auctions or auctions[0]["status"] == "completed":
            raise ValueError("Invalid invitation or auction no longer open.")

        # Any failure rolls back both saves, including a duplicate team name.
        user = set_user(auth_issuer, auth_subject, username, connection=conn)
        return set_fanta_manager(user["id"], auctions[0]["id"], team_name, connection=conn)
