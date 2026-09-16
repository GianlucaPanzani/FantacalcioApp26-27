"""Exercise SQLite persistence and auction integrity without Streamlit or live data."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.backend import api


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db_path = Path(self.temporary.name) / "nested" / "auction.sqlite3"
        database_patch = patch.object(api, "DB_PATH", self.db_path)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        api.create()

    def insert_row(self, table, *, connection=None, **fields):
        """Keep test fixtures readable while using the public multi-column API."""
        return api.insert(
            table, tuple(fields), tuple(fields.values()), connection=connection,
        )

    def make_auction(self, label):
        """Create two independent auctions when testing cross-auction references."""
        user_id = self.insert_row("users", username=f"host_{label}")
        auction_id = self.insert_row(
            "auctions", name=label, season="2026-27", host_user_id=user_id,
            invite_code_hash=hashlib.sha256(label.encode()).hexdigest(),
        )
        participant_id = self.insert_row(
            "participants", auction_id=auction_id, user_id=user_id,
            team_name=f"Team {label}",
        )
        player_id = self.insert_row(
            "players", auction_id=auction_id, source_id=123,
            player="Example player", team="Example club", fanta_role="A",
            mantra_role="Pc",
        )
        lot_id = self.insert_row(
            "auction_lots", auction_id=auction_id, player_id=player_id,
        )
        return {
            "user_id": user_id, "auction_id": auction_id,
            "participant_id": participant_id, "player_id": player_id,
            "lot_id": lot_id,
        }

    def test_create_is_idempotent_and_data_persists_between_connections(self):
        user_id = api.insert("users", "username", "Persistent user")
        self.assertEqual(api.create(), self.db_path.resolve())
        self.assertTrue(self.db_path.is_file())
        self.assertEqual(api.get("users", "id", user_id)[0]["username"], "Persistent user")
        with closing(sqlite3.connect(self.db_path)) as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue({
                "users", "auctions", "participants", "players", "auction_lots",
                "bids", "purchases", "participant_settings", "player_preferences",
            }.issubset(tables))
            self.assertEqual(
                connection.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone(),
                ("Persistent user",),
            )
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_auction_defaults_match_current_settings_and_reject_invalid_limits(self):
        fixture = self.make_auction("defaults")
        row = api.get("auctions", "id", fixture["auction_id"])[0]
        expected = {
            "status": "lobby", "total_budget": 500,
            "goalkeeper_slots": 3, "defender_slots": 8,
            "midfielder_slots": 8, "forward_slots": 6,
            "defender_modifier_enabled": 0, "midfielder_modifier_enabled": 0,
            "player_switch_enabled": 0,
            "points_goal_scored": 3.0, "points_goalkeeper_goal_conceded": -1.0,
            "points_assist": 1.0, "points_penalty_scored": 3.0,
            "points_penalty_missed": -3.0, "points_goalkeeper_penalty_conceded": -1.0,
            "points_goalkeeper_penalty_saved": 3.0, "points_yellow_card": -0.5,
            "points_red_card": -1.0,
        }
        self.assertEqual({column: row[column] for column in expected}, expected)
        for column, value in (
            ("total_budget", -1), ("forward_slots", -1),
            ("defender_modifier_enabled", 2), ("status", "unknown"),
        ):
            with self.subTest(column=column), self.assertRaises(sqlite3.IntegrityError):
                api.update("auctions", column, value, where={"id": fixture["auction_id"]})
        api.update(
            "auctions", ["total_budget", "forward_slots"], [0, 0],
            where={"id": fixture["auction_id"]},
        )
        row = api.get("auctions", "id", fixture["auction_id"])[0]
        self.assertEqual((row["total_budget"], row["forward_slots"]), (0, 0))

    def test_crud_supports_null_and_multiple_column_filters(self):
        first_id = api.insert("users", "username", "First")
        second_id = self.insert_row(
            "users", username="Second", auth_issuer="issuer", auth_subject="subject",
        )
        self.assertIsInstance(first_id, int)
        self.assertEqual(len(api.get("users", None, None)), 2)
        self.assertEqual(api.get("users", "auth_subject", None)[0]["id"], first_id)
        self.assertEqual(
            api.get("users", ["auth_issuer", "auth_subject"], ["issuer", "subject"])[0]["id"],
            second_id,
        )
        self.assertEqual(
            api.update("users", "username", "Renamed", where={"id": first_id}), 1,
        )
        self.assertEqual(
            api.update(
                "users", ("auth_issuer", "auth_subject"), (None, None),
                where={"id": second_id, "username": "Second"},
            ),
            1,
        )
        self.assertEqual(len(api.get("users", "auth_subject", None)), 2)
        self.assertEqual(
            api.remove("users", ("id", "username"), (first_id, "Renamed")), 1,
        )
        self.assertEqual(api.get("users", "id", first_id), [])
        self.assertEqual(api.remove("users", "id", first_id), 0)
        self.assertEqual(api.update("users", "username", "Absent", where={"id": -1}), 0)

    def test_values_are_bound_and_identifiers_are_validated(self):
        payload = "Robert'); DROP TABLE users; --"
        user_id = api.insert("users", "username", payload)
        self.assertEqual(api.get("users", "username", payload)[0]["id"], user_id)
        for table, column in (
            ("users; DROP TABLE users", "id"),
            ("sqlite_master", "name"),
            ("users", "id OR 1=1"),
            ("users", "missing_column"),
        ):
            with self.subTest(table=table, column=column):
                with self.assertRaises(ValueError):
                    api.get(table, column, user_id)
        with self.assertRaises(ValueError):
            api.update("users", "username", "Changed", where={"id OR 1=1": user_id})
        self.assertEqual(api.get("users", "id", user_id)[0]["username"], payload)

    def test_malformed_arguments_and_unfiltered_mutations_are_rejected(self):
        invalid_calls = (
            lambda: api.get("users", ["id", "username"], [1]),
            lambda: api.get("users", None, "unexpected"),
            lambda: api.insert("users", ["username", "auth_subject"], ["Only one"]),
            lambda: api.insert("users", [], []),
            lambda: api.update("users", "username", "Changed", where={}),
            lambda: api.remove("users", None, None),
            lambda: api.remove("users", [], []),
        )
        for index, operation in enumerate(invalid_calls):
            with self.subTest(operation=index):
                with self.assertRaises(ValueError):
                    operation()

    def test_user_identity_is_unique_and_provider_claims_are_paired(self):
        self.insert_row("users", username="Alice", auth_issuer="issuer", auth_subject="123")
        for fields in (
            {"username": "alice"},
            {"username": "Other", "auth_issuer": "issuer", "auth_subject": "123"},
            {"username": "Incomplete", "auth_subject": "123"},
            {"username": "Incomplete", "auth_issuer": "issuer"},
        ):
            with self.subTest(fields=fields), self.assertRaises(sqlite3.IntegrityError):
                self.insert_row("users", **fields)
        self.insert_row("users", username="Another provider", auth_issuer="other", auth_subject="123")
        self.assertEqual(len(api.get("users", None, None)), 2)

    def test_participant_uniqueness_is_scoped_to_each_auction(self):
        first = self.make_auction("first")
        second = self.make_auction("second")
        guest_id = api.insert("users", "username", "Guest")
        self.insert_row(
            "participants", auction_id=first["auction_id"], user_id=guest_id, team_name="Guest team",
        )
        for user_id, team_name in ((guest_id, "Another team"), (second["user_id"], "Guest team")):
            with self.subTest(user_id=user_id), self.assertRaises(sqlite3.IntegrityError):
                self.insert_row(
                    "participants", auction_id=first["auction_id"],
                    user_id=user_id, team_name=team_name,
                )
        self.insert_row(
            "participants", auction_id=second["auction_id"], user_id=guest_id, team_name="Guest team",
        )

    def test_foreign_keys_are_enabled_for_every_write(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("participants", auction_id=999, user_id=999, team_name="Orphan")
        fixture = self.make_auction("valid")
        with self.assertRaises(sqlite3.IntegrityError):
            api.update(
                "participants", "user_id", 999, where={"id": fixture["participant_id"]},
            )
        self.assertEqual(
            api.get("participants", "id", fixture["participant_id"])[0]["user_id"],
            fixture["user_id"],
        )

    def test_one_open_lot_per_auction_allows_reauction_after_skip(self):
        fixture = self.make_auction("one_open")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row(
                "auction_lots", auction_id=fixture["auction_id"], player_id=fixture["player_id"],
            )
        api.update("auction_lots", "status", "skipped", where={"id": fixture["lot_id"]})
        new_lot = self.insert_row(
            "auction_lots", auction_id=fixture["auction_id"], player_id=fixture["player_id"],
        )
        self.assertNotEqual(new_lot, fixture["lot_id"])
        self.assertEqual(len(api.get("auction_lots", "auction_id", fixture["auction_id"])), 2)

    def test_cross_auction_references_are_rejected(self):
        first = self.make_auction("first")
        second = self.make_auction("second")
        invalid_rows = (
            ("auction_lots", {
                "auction_id": first["auction_id"], "player_id": second["player_id"], "status": "skipped",
            }),
            ("bids", {
                "auction_id": first["auction_id"], "lot_id": first["lot_id"],
                "participant_id": second["participant_id"], "amount": 5,
            }),
            ("bids", {
                "auction_id": first["auction_id"], "lot_id": second["lot_id"],
                "participant_id": first["participant_id"], "amount": 5,
            }),
            ("purchases", {
                "auction_id": first["auction_id"], "lot_id": first["lot_id"],
                "participant_id": second["participant_id"], "player_id": first["player_id"], "price": 5,
            }),
            ("player_preferences", {
                "auction_id": first["auction_id"], "participant_id": first["participant_id"],
                "player_id": second["player_id"],
            }),
        )
        for table, fields in invalid_rows:
            with self.subTest(table=table, fields=fields), self.assertRaises(sqlite3.IntegrityError):
                self.insert_row(table, **fields)

    def test_bid_values_and_uniqueness_are_enforced(self):
        fixture = self.make_auction("bids")
        fields = {
            "auction_id": fixture["auction_id"], "lot_id": fixture["lot_id"],
            "participant_id": fixture["participant_id"],
        }
        for amount in (-1, 1.5, "not a number"):
            with self.subTest(amount=amount), self.assertRaises(sqlite3.IntegrityError):
                self.insert_row("bids", **fields, amount=amount)
        bid_id = self.insert_row("bids", **fields, amount=0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("bids", **fields, amount=5)
        api.update("bids", "amount", 5, where={"id": bid_id})
        self.assertEqual(api.get("bids", "id", bid_id)[0]["amount"], 5)

    def test_purchase_must_match_lot_player_and_player_has_one_owner(self):
        fixture = self.make_auction("purchases")
        second_player = self.insert_row(
            "players", auction_id=fixture["auction_id"], source_id=456,
            player="Other player", fanta_role="D",
        )
        fields = {
            "auction_id": fixture["auction_id"], "lot_id": fixture["lot_id"],
            "participant_id": fixture["participant_id"],
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("purchases", **fields, player_id=second_player, price=10)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("purchases", **fields, player_id=fixture["player_id"], price=0)
        self.insert_row("purchases", **fields, player_id=fixture["player_id"], price=10)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("purchases", **fields, player_id=fixture["player_id"], price=20)
        api.update("auction_lots", "status", "sold", where={"id": fixture["lot_id"]})
        second_lot = self.insert_row(
            "auction_lots", auction_id=fixture["auction_id"], player_id=fixture["player_id"],
        )
        fields["lot_id"] = second_lot
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("purchases", **fields, player_id=fixture["player_id"], price=20)

    def test_settings_json_and_player_preferences_are_persisted(self):
        fixture = self.make_auction("preferences")
        key = "settings_A_budget_limit_key"
        settings_id = self.insert_row(
            "participant_settings", participant_id=fixture["participant_id"], key=key, value_json="150",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row(
                "participant_settings", participant_id=fixture["participant_id"], key=key, value_json="200",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            api.update("participant_settings", "value_json", "not JSON", where={"id": settings_id})
        self.assertEqual(api.get("participant_settings", "id", settings_id)[0]["value_json"], "150")
        fields = {
            "auction_id": fixture["auction_id"], "participant_id": fixture["participant_id"],
            "player_id": fixture["player_id"],
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("player_preferences", **fields, max_bid=-1)
        preference_id = self.insert_row(
            "player_preferences", **fields, max_bid=50, interest="Altissimo", description="Watch this player",
        )
        self.assertEqual(api.get("player_preferences", "id", preference_id)[0]["description"], "Watch this player")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("player_preferences", **fields, max_bid=100)

    def test_transactions_commit_as_a_unit_and_roll_back_on_failure(self):
        with api.transaction() as connection:
            self.insert_row("users", username="Committed", connection=connection)
            self.assertEqual(len(api.get("users", None, None, connection=connection)), 1)
        self.assertEqual(len(api.get("users", None, None)), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            with api.transaction() as connection:
                self.insert_row("users", username="Rolled back", connection=connection)
                self.insert_row("users", username="Committed", connection=connection)
        self.assertEqual(api.get("users", "username", "Rolled back"), [])
        self.assertEqual(api.get("users", None, None)[0]["username"], "Committed")

    def test_remove_protects_auction_history_and_cascades_personal_preferences(self):
        fixture = self.make_auction("removal")
        participant_id = fixture["participant_id"]
        self.insert_row(
            "participant_settings", participant_id=participant_id,
            key="settings_A_budget_limit_key", value_json="150",
        )
        self.insert_row(
            "player_preferences", auction_id=fixture["auction_id"],
            participant_id=participant_id, player_id=fixture["player_id"], max_bid=50,
        )
        bid_id = self.insert_row(
            "bids", auction_id=fixture["auction_id"], lot_id=fixture["lot_id"],
            participant_id=participant_id, amount=5,
        )
        for table, record_id in (
            ("users", fixture["user_id"]), ("auctions", fixture["auction_id"]),
            ("players", fixture["player_id"]), ("auction_lots", fixture["lot_id"]),
            ("participants", participant_id),
        ):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                api.remove(table, "id", record_id)
        self.assertEqual(len(api.get("participant_settings", "participant_id", participant_id)), 1)
        self.assertEqual(len(api.get("player_preferences", "participant_id", participant_id)), 1)
        self.assertEqual(api.remove("bids", "id", bid_id), 1)
        self.assertEqual(api.remove("participants", "id", participant_id), 1)
        self.assertEqual(api.get("participant_settings", "participant_id", participant_id), [])
        self.assertEqual(api.get("player_preferences", "participant_id", participant_id), [])
        self.assertEqual(len(api.get("auction_lots", "id", fixture["lot_id"])), 1)

    def test_failed_multirow_update_does_not_partially_modify_users(self):
        api.insert("users", "username", "First")
        api.insert("users", "username", "Second")
        with self.assertRaises(sqlite3.IntegrityError):
            api.update("users", "username", "Duplicate", where={"auth_subject": None})
        self.assertEqual(
            {row["username"] for row in api.get("users", None, None)}, {"First", "Second"},
        )

    def test_concurrent_duplicate_registration_has_one_winner(self):
        barrier = threading.Barrier(2)

        def register():
            barrier.wait(timeout=5)
            try:
                api.insert("users", "username", "Concurrent guest")
            except sqlite3.IntegrityError:
                return "duplicate"
            return "inserted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(register) for _ in range(2)]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(outcomes, ["inserted", "duplicate"])
        self.assertEqual(len(api.get("users", "username", "Concurrent guest")), 1)


if __name__ == "__main__":
    unittest.main()
