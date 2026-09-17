"""Test identity and Fanta Manager lookups without Google or Streamlit."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.backend import api
from src.backend.auction_services import get_fanta_manager, register_to_auction, set_fanta_manager
from src.backend.user_services import get_user, set_user


class IdentityServicesTests(unittest.TestCase):
    def setUp(self):
        """Create an isolated temporary database for each test."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = patch.object(api, "DB_PATH", Path(directory.name) / "identity.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        api.create_db()

    def insert_row(self, table, **fields):
        """Insert a fixture row using the public database API."""
        return api.insert(table, fields)

    def create_auction(self, invite_code="JOIN-ME", status="lobby"):
        """Create an auction fixture and return its identifier."""
        host_id = api.insert("users", {"username": f"Host {invite_code}"})
        return self.insert_row(
            "auctions", name="Test auction", season="2026-27", host_user_id=host_id,
            invite_code_hash=hashlib.sha256(invite_code.encode()).hexdigest(), status=status,
        )

    def test_missing_identity_and_fanta_manager_do_not_create_records(self):
        """Return no data and perform no writes for missing lookups."""
        self.assertIsNone(get_user("https://accounts.google.com", "new-subject"))
        self.assertIsNone(get_fanta_manager(user_id=1, auction_id=1))
        self.assertEqual(api.get("users"), [])
        self.assertEqual(api.get("fanta_managers"), [])

    def test_identity_lookup_uses_both_provider_and_subject(self):
        """Distinguish equal subjects issued by different providers."""
        first_id = self.insert_row(
            "users", username="Mario", auth_issuer="google", auth_subject="123",
        )
        second_id = self.insert_row(
            "users", username="Luigi", auth_issuer="other-provider", auth_subject="123",
        )
        self.assertEqual(get_user("google", "123")["id"], first_id)
        self.assertEqual(get_user("other-provider", "123")["id"], second_id)
        self.assertIsNone(get_user("google", "another-subject"))

        # Renaming the account must not change the identity used for login.
        api.update("users", {"username": "Mario92"}, {"id": first_id})
        self.assertEqual(get_user("google", "123")["username"], "Mario92")

    def test_fanta_manager_lookup_is_scoped_to_user_and_auction(self):
        """Return only the team managed by the user in the requested auction."""
        user_id = api.insert("users", {"username": "Guest"})
        another_user = api.insert("users", {"username": "Another guest"})
        for label in ("First", "Second"):
            auction_id = self.insert_row(
                "auctions", name=label, season="2026-27", host_user_id=user_id,
                invite_code_hash=f"test-invitation-{label}",
            )
            fanta_manager_id = self.insert_row(
                "fanta_managers", user_id=user_id, auction_id=auction_id,
                team_name=f"{label} team",
            )
            fanta_manager = get_fanta_manager(user_id, auction_id)
            self.assertEqual(fanta_manager["id"], fanta_manager_id)
            self.assertEqual(fanta_manager["team_name"], f"{label} team")
            self.assertIsNone(get_fanta_manager(another_user, auction_id))
        self.assertIsNone(get_fanta_manager(user_id, 999))

    def test_set_user_creates_and_updates_only_the_same_identity(self):
        """Create one account per identity and update only that account."""
        user = set_user("google", "123", " Mario ")
        self.assertEqual(user["username"], "Mario")
        renamed = set_user("google", "123", "Mario92")
        self.assertEqual(renamed["id"], user["id"])
        self.assertEqual(renamed["username"], "Mario92")
        with self.assertRaises(sqlite3.IntegrityError):
            set_user("google", "456", "mario92")
        self.assertIsNone(get_user("google", "456"))
        self.assertEqual(len(api.get("users")), 1)

    def test_set_fanta_manager_updates_only_the_requested_auction(self):
        """Rename a managed team without changing another auction."""
        first_auction = self.create_auction("FIRST")
        second_auction = self.create_auction("SECOND")
        user = set_user("google", "123", "Guest")
        first = set_fanta_manager(user["id"], first_auction, " First FC ")
        second = set_fanta_manager(user["id"], second_auction, "Second FC")
        renamed = set_fanta_manager(user["id"], first_auction, "Renamed FC")
        self.assertEqual(first["team_name"], "First FC")
        self.assertEqual(renamed["id"], first["id"])
        self.assertEqual(renamed["team_name"], "Renamed FC")
        self.assertEqual(get_fanta_manager(user["id"], second_auction), second)

    def test_registration_is_repeatable_and_zip_import_is_deferred(self):
        """Reuse one Fanta Manager record and defer personal backup import."""
        auction_id = self.create_auction()
        fanta_manager = register_to_auction(
            "google", "123", "Mario", " JOIN-ME ", "Mario FC",
        )
        repeated = register_to_auction(
            "google", "123", "Mario", "JOIN-ME", "Mario FC", zip_archive=b"not processed yet",
        )
        self.assertEqual(repeated, fanta_manager)
        self.assertEqual(fanta_manager["auction_id"], auction_id)
        self.assertEqual(fanta_manager["user_id"], get_user("google", "123")["id"])
        self.assertEqual(len(api.get("fanta_managers")), 1)
        self.assertEqual(api.get("settings"), [])
        self.assertEqual(api.get("players_selected"), [])

    def test_invalid_invitation_or_completed_auction_does_not_create_account(self):
        """Reject unknown or completed auctions without creating an account."""
        self.create_auction(status="completed")
        for invite_code in ("UNKNOWN", "JOIN-ME"):
            with self.subTest(invite_code=invite_code), self.assertRaises(ValueError):
                register_to_auction("google", "123", "Guest", invite_code, "Guest FC")
            self.assertIsNone(get_user("google", "123"))
        self.assertEqual(api.get("fanta_managers"), [])

    def test_duplicate_team_rolls_back_account_creation_or_rename(self):
        """Roll back account changes when a team name is already used."""
        self.create_auction()
        register_to_auction("google", "owner", "Owner", "JOIN-ME", "Taken FC")
        with self.assertRaises(sqlite3.IntegrityError):
            register_to_auction("google", "new", "New guest", "JOIN-ME", "taken fc")
        self.assertIsNone(get_user("google", "new"))

        existing = set_user("google", "existing", "Original name")
        with self.assertRaises(sqlite3.IntegrityError):
            register_to_auction("google", "existing", "Changed name", "JOIN-ME", "Taken FC")
        self.assertEqual(get_user("google", "existing"), existing)
        self.assertEqual(len(api.get("fanta_managers")), 1)

    def test_empty_names_are_rejected_without_partial_registration(self):
        """Reject empty account or team names without partial writes."""
        self.create_auction()
        for username, team_name in ((" ", "Guest FC"), ("Guest", " ")):
            with self.subTest(username=username, team_name=team_name), self.assertRaises(ValueError):
                register_to_auction("google", "123", username, "JOIN-ME", team_name)
            self.assertIsNone(get_user("google", "123"))
        self.assertEqual(api.get("fanta_managers"), [])

    def test_concurrent_repeated_registration_creates_one_fanta_manager(self):
        """Create one account and managed team during concurrent registration."""
        self.create_auction()
        barrier = threading.Barrier(2)

        def register():
            """Submit the same registration after both workers are ready."""
            barrier.wait(timeout=5)
            return register_to_auction("google", "123", "Guest", "JOIN-ME", "Guest FC")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(register) for _ in range(2)]
            first, second = [future.result(timeout=15) for future in futures]
        self.assertEqual(first, second)
        self.assertEqual(len(api.get("users", {"auth_subject": "123"})), 1)
        self.assertEqual(len(api.get("fanta_managers")), 1)


if __name__ == "__main__":
    unittest.main()
