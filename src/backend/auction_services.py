

from contextlib import nullcontext
import hashlib
import sqlite3

from . import api
from .user_services import set_user


def get_participant(
    user_id: int, auction_id: int, *, connection: sqlite3.Connection | None = None,
) -> dict | None:
    """Return the user's participation in the requested auction, or None."""
    # Scope the lookup to one auction, since a user can join several auctions.
    participants = api.get(
        table="participants",
        columns=["user_id", "auction_id"],
        values=[user_id, auction_id],
        connection=connection,
    )
    return participants[0] if participants else None


def get_participants(
    auction_id: int, *, connection: sqlite3.Connection | None = None,
) -> dict | None:
    participants = api.get(
        table="participants",
        columns=["auction_id"],
        values=[auction_id],
        connection=connection,
    )
    return participants


def set_partecipant(
    user_id: int, auction_id: int, team_name: str, *,
    connection: sqlite3.Connection | None = None,
) -> dict:
    """Create or rename a user's team in an auction and return its participation."""
    # Keep one participation per user and auction; the database checks duplicates.
    team_name = team_name.strip()
    if not team_name:
        raise ValueError("Enter a team name.")

    context = api.transaction() if connection is None else nullcontext(connection)
    with context as conn:
        participant = get_partecipation(user_id, auction_id, connection=conn)
        if participant is None:
            api.insert(
                "participants", ["user_id", "auction_id", "team_name"],
                [user_id, auction_id, team_name], connection=conn,
            )
        else:
            api.update(
                "participants", "team_name", team_name,
                where={"id": participant["id"]}, connection=conn,
            )

        return get_partecipation(user_id, auction_id, connection=conn)


def register_to_auction(
    auth_issuer: str, auth_subject: str, username: str,
    invite_code: str, team_name: str, zip_archive: bytes | None = None,
) -> dict:
    """Save the account and membership together. ZIP import is deferred."""
    
    # Match the invitation to an auction that still accepts registrations.
    invite_hash = hashlib.sha256(invite_code.strip().encode("utf-8")).hexdigest()
    with api.transaction() as conn:
        auctions = api.get("auctions", "invite_code_hash", invite_hash, connection=conn)
        if not auctions or auctions[0]["status"] == "completed":
            raise ValueError("Invalid invitation or auction no longer open.")

        # Any failure rolls back both saves, including a duplicate team name.
        user = set_user(auth_issuer, auth_subject, username, connection=conn)
        return set_partecipant(user["id"], auctions[0]["id"], team_name, connection=conn)
