"""Test user and Fanta Manager database modules without live authentication."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.backend import db_api
from src.backend.auctions_db import set_auction
from src.backend.fanta_managers_db import (
    get_fanta_manager,
    get_fanta_managers,
    register_to_auction,
    set_fanta_manager,
    update_fanta_manager,
)
from src.backend.users_db import get_user, get_users, set_user, update_user


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

    def create_user(self, label: str, **extra_data) -> dict:
        """Insert and return a user fixture with a unique team name."""
        return set_user({
            "username": label,
            "team_name": f"{label} FC",
            **extra_data,
        })

    def create_auction(self, invite_code="JOIN-ME", status="lobby") -> int:
        """Create an auction fixture and return its identifier."""
        host = self.create_user(f"Host {invite_code}")
        auction = set_auction({
            "name": f"Test auction {invite_code}",
            "season": "2026-27",
            "host_user_id": host["id"],
            "invite_code_hash": hashlib.sha256(invite_code.encode()).hexdigest(),
            "status": status,
        })
        return auction["id"]

    def find_identity(self, issuer: str, subject: str) -> dict | None:
        """Return the first user matching an OIDC identity."""
        users = get_users({"auth_issuer": issuer, "auth_subject": subject})
        return users[0] if users else None

    def test_missing_records_do_not_create_data(self):
        """Return no data and perform no writes for missing lookups."""
        self.assertIsNone(get_user(1))
        self.assertIsNone(get_fanta_manager(1))
        self.assertEqual(get_users(), [])
        self.assertEqual(get_fanta_managers(), [])

    def test_identity_lookup_uses_both_provider_and_subject(self):
        """Distinguish equal subjects issued by different providers."""
        first = self.create_user(
            "Mario",
            auth_issuer="google",
            auth_subject="123",
        )
        second = self.create_user(
            "Luigi",
            auth_issuer="other-provider",
            auth_subject="123",
        )
        self.assertEqual(self.find_identity("google", "123"), first)
        self.assertEqual(self.find_identity("other-provider", "123"), second)
        self.assertIsNone(self.find_identity("google", "another-subject"))

    def test_user_set_and_update_use_dictionaries(self):
        """Insert a user from one dictionary and update it by identifier."""
        user = set_user({
            "auth_issuer": "google",
            "auth_subject": "123",
            "username": "Mario",
            "team_name": "Mario FC",
        })
        renamed = update_user(
            user["id"],
            {"username": "Mario92", "team_name": "New Mario FC"},
        )
        self.assertEqual(renamed["id"], user["id"])
        self.assertEqual(renamed["username"], "Mario92")
        self.assertEqual(renamed["team_name"], "New Mario FC")

        with self.assertRaises(sqlite3.IntegrityError):
            set_user({
                "auth_issuer": "google",
                "auth_subject": "456",
                "username": "mario92",
                "team_name": "Other FC",
            })

    def test_fanta_manager_set_and_update_use_dictionaries(self):
        """Insert and update a Fanta Manager through its table module."""
        auction_id = self.create_auction()
        first_user = self.create_user("First manager")
        second_user = self.create_user("Second manager")
        fanta_manager = set_fanta_manager({
            "auction_id": auction_id,
            "user_id": first_user["id"],
        })
        updated = update_fanta_manager(
            fanta_manager["id"],
            {"user_id": second_user["id"]},
        )
        self.assertEqual(updated["id"], fanta_manager["id"])
        self.assertEqual(updated["user_id"], second_user["id"])

    def test_registration_is_repeatable_and_zip_import_is_deferred(self):
        """Reuse one user and Fanta Manager while deferring backup import."""
        auction_id = self.create_auction()
        fanta_manager = register_to_auction(
            "google", "123", "Mario", " JOIN-ME ", "Mario FC",
        )
        repeated = register_to_auction(
            "google",
            "123",
            "Mario",
            "JOIN-ME",
            "Mario FC",
            zip_archive=b"not processed yet",
        )
        self.assertEqual(repeated, fanta_manager)
        self.assertEqual(fanta_manager["auction_id"], auction_id)
        user = self.find_identity("google", "123")
        self.assertEqual(fanta_manager["user_id"], user["id"])
        self.assertEqual(user["team_name"], "Mario FC")
        self.assertEqual(len(get_fanta_managers()), 1)

    def test_invalid_invitation_or_completed_auction_does_not_create_account(self):
        """Reject unknown or completed auctions without creating an account."""
        self.create_auction(status="completed")
        for invite_code in ("UNKNOWN", "JOIN-ME"):
            with self.subTest(invite_code=invite_code), self.assertRaises(ValueError):
                register_to_auction(
                    "google", "123", "Guest", invite_code, "Guest FC",
                )
            self.assertIsNone(self.find_identity("google", "123"))
        self.assertEqual(get_fanta_managers(), [])

    def test_duplicate_team_rolls_back_account_creation_or_update(self):
        """Roll back account changes when a team name is already used."""
        self.create_auction()
        register_to_auction(
            "google", "owner", "Owner", "JOIN-ME", "Taken FC",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            register_to_auction(
                "google", "new", "New guest", "JOIN-ME", "taken fc",
            )
        self.assertIsNone(self.find_identity("google", "new"))

        existing = self.create_user(
            "Original name",
            auth_issuer="google",
            auth_subject="existing",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            register_to_auction(
                "google", "existing", "Changed name", "JOIN-ME", "Taken FC",
            )
        self.assertEqual(get_user(existing["id"]), existing)
        self.assertEqual(len(get_fanta_managers()), 1)

    def test_empty_names_are_rejected_without_partial_registration(self):
        """Reject empty account or team names without partial writes."""
        self.create_auction()
        for username, team_name in ((" ", "Guest FC"), ("Guest", " ")):
            with self.subTest(username=username, team_name=team_name):
                with self.assertRaises(ValueError):
                    register_to_auction(
                        "google", "123", username, "JOIN-ME", team_name,
                    )
            self.assertIsNone(self.find_identity("google", "123"))
        self.assertEqual(get_fanta_managers(), [])

    def test_concurrent_repeated_registration_creates_one_fanta_manager(self):
        """Create one account and managed team during concurrent registration."""
        self.create_auction()
        barrier = threading.Barrier(2)

        def register():
            """Submit the same registration after both workers are ready."""
            barrier.wait(timeout=5)
            return register_to_auction(
                "google", "123", "Guest", "JOIN-ME", "Guest FC",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(register) for _ in range(2)]
            first, second = [future.result(timeout=15) for future in futures]
        self.assertEqual(first, second)
        self.assertEqual(len(get_users({"auth_subject": "123"})), 1)
        self.assertEqual(len(get_fanta_managers()), 1)


if __name__ == "__main__":
    unittest.main()
