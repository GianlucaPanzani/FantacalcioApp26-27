"""Test user identity and auction registration without live authentication."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import db_api
from backend.auctions_db import set_auction
from backend.services import register_to_auction, register_user
from backend.users_db import get_users, set_user


class IdentityServicesTests(unittest.TestCase):
    def setUp(self):
        """Create an isolated temporary database for each test."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = patch.object(
            db_api,
            "DB_PATH",
            Path(directory.name) / "identity.sqlite3",
        )
        database.start()
        self.addCleanup(database.stop)
        db_api.create_db()

    def create_auction(self, auction_code="JOIN-ME", status="lobby") -> int:
        """Create an auction and return its identifier."""
        host = set_user({"username": "Host", "team_name": "Host FC"})
        auction = set_auction({
            "name": "Test auction",
            "season": "2026-27",
            "host_user_id": host["id"],
            "auction_code_hash": hashlib.sha256(auction_code.encode()).hexdigest(),
            "status": status,
        })
        return auction["id"]

    def test_registration_associates_user_directly_with_auction(self):
        """Create one user whose auction ID identifies its lobby."""
        auction_id = self.create_auction()
        data = {
            "auth_issuer": "google",
            "auth_subject": "123",
            "username": "Mario",
            "team_name": "Mario FC",
        }
        registered = register_user(data)
        user = register_to_auction(registered["id"], " JOIN-ME ")
        repeated = register_to_auction(registered["id"], "JOIN-ME")

        self.assertEqual(repeated["id"], user["id"])
        self.assertEqual(user["current_auction_id"], auction_id)
        self.assertEqual(len(get_users({"current_auction_id": auction_id})), 1)

    def test_invalid_invitation_does_not_create_account(self):
        """Reject an unknown invitation without a partial user insert."""
        self.create_auction()
        user = register_user({
            "auth_issuer": "google",
            "auth_subject": "123",
            "username": "Guest",
            "team_name": "Guest FC",
        })
        with self.assertRaises(ValueError):
            register_to_auction(user["id"], "UNKNOWN")
        self.assertIsNone(get_users({"auth_subject": "123"})[0]["current_auction_id"])


if __name__ == "__main__":
    unittest.main()
