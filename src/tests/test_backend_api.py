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

from src.backend import db_api as api


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        """Create an isolated temporary database for each test."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db_path = Path(self.temporary.name) / "nested" / "auction.sqlite3"
        database_patch = patch.object(api, "DB_PATH", self.db_path)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        api.create_db()

    def insert_row(self, table, connection=None, **fields):
        """Insert a fixture row through the public dictionary API."""
        if table == "users":
            fields.setdefault("team_name", f"Team {fields.get('username', 'user')}")
        return api.insert(table, fields, connection=connection)

    def make_auction(self, label):
        """Create an auction with one Fanta Manager and one catalog player."""
        user_id = self.insert_row("users", username=f"host_{label}")
        auction_id = self.insert_row(
            "auctions", name=label, season="2026-27", host_user_id=user_id,
            invite_code_hash=hashlib.sha256(label.encode()).hexdigest(),
        )
        fanta_manager_id = self.insert_row(
            "fanta_managers", auction_id=auction_id, user_id=user_id,
        )
        player_id = self.insert_row(
            "players", auction_id=auction_id, source_id=123,
            player="Example player", team="Example club", fanta_role="A",
            mantra_role="Pc",
        )
        return {
            "user_id": user_id,
            "auction_id": auction_id,
            "fanta_manager_id": fanta_manager_id,
            "player_id": player_id,
        }

    def test_create_db_is_idempotent_and_data_persists_between_connections(self):
        """Keep existing rows when database initialization runs more than once."""
        user_id = api.insert(
            "users",
            {"username": "Persistent user", "team_name": "Persistent team"},
        )
        self.assertEqual(api.create_db(), self.db_path.resolve())
        self.assertTrue(self.db_path.is_file())
        self.assertEqual(
            api.get("users", {"id": user_id})[0]["username"],
            "Persistent user",
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue({
                "users", "auctions", "fanta_managers", "players", "purchases",
                "settings",
            }.issubset(tables))
            self.assertNotIn("players_selected", tables)
            self.assertTrue({"auction_lots", "bids"}.isdisjoint(tables))
            indexes = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            self.assertTrue({
                "auctions_by_host", "fanta_managers_by_user",
                "purchases_by_fanta_manager",
            }.issubset(indexes))
            self.assertNotIn("players_selected_by_player", indexes)
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_reset_db_removes_database_and_companion_files(self):
        """Delete all SQLite files and allow explicit recreation afterwards."""
        Path(f"{self.db_path}-wal").touch()
        Path(f"{self.db_path}-shm").touch()
        api.reset_db()
        self.assertFalse(self.db_path.exists())
        self.assertFalse(Path(f"{self.db_path}-wal").exists())
        self.assertFalse(Path(f"{self.db_path}-shm").exists())
        api.reset_db()
        self.assertEqual(api.create_db(), self.db_path.resolve())

    def test_auction_defaults_match_current_settings_and_reject_invalid_limits(self):
        """Apply current auction defaults and reject values outside constraints."""
        fixture = self.make_auction("defaults")
        row = api.get("auctions", {"id": fixture["auction_id"]})[0]
        expected = {
            "status": "lobby", "total_budget": 500,
            "goalkeeper_slots": 3, "defender_slots": 8,
            "midfielder_slots": 8, "forward_slots": 6,
            "defender_modifier_enabled": 0, "midfielder_modifier_enabled": 0,
            "player_switch_enabled": 0,
            "player_extraction_order": "random",
            "player_extraction_scope": "on_all_players",
            "role_extraction_order": "in_order_P_D_C_A",
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
            ("player_extraction_order", "manual"),
            ("player_extraction_scope", "unknown"),
            ("role_extraction_order", "alphabetic_order"),
        ):
            with self.subTest(column=column), self.assertRaises(sqlite3.IntegrityError):
                api.update(
                    "auctions",
                    {column: value},
                    {"id": fixture["auction_id"]},
                )

    def test_crud_supports_null_and_multiple_column_filters(self):
        """Read, update, and remove rows with dictionary filters."""
        first_id = api.insert(
            "users",
            {"username": "First", "team_name": "First team"},
        )
        second_id = self.insert_row(
            "users", username="Second", auth_issuer="issuer", auth_subject="subject",
        )
        self.assertEqual(len(api.get("users")), 2)
        self.assertEqual(api.get("users", {"auth_subject": None})[0]["id"], first_id)
        self.assertEqual(
            api.get(
                "users",
                {"auth_issuer": "issuer", "auth_subject": "subject"},
            )[0]["id"],
            second_id,
        )
        self.assertEqual(
            api.update("users", {"username": "Renamed"}, {"id": first_id}),
            1,
        )
        self.assertEqual(api.remove("users", {"id": first_id}), 1)
        self.assertEqual(api.get("users", {"id": first_id}), [])

    def test_values_are_bound_and_identifiers_are_validated(self):
        """Bind values safely and reject tables or columns outside the schema."""
        payload = "Robert'); DROP TABLE users; --"
        user_id = api.insert(
            "users",
            {"username": payload, "team_name": "Safe team"},
        )
        self.assertEqual(api.get("users", {"username": payload})[0]["id"], user_id)
        for table, column in (
            ("users; DROP TABLE users", "id"),
            ("sqlite_master", "name"),
            ("users", "id OR 1=1"),
            ("users", "missing_column"),
        ):
            with self.subTest(table=table, column=column), self.assertRaises(ValueError):
                api.get(table, {column: user_id})

    def test_malformed_arguments_and_unfiltered_mutations_are_rejected(self):
        """Reject malformed dictionaries and mutations without safe filters."""
        invalid_calls = (
            lambda: api.get("users", [("id", 1)]),
            lambda: api.insert("users", [("username", "Only one")]),
            lambda: api.insert("users", {}),
            lambda: api.update("users", {"username": "Changed"}, {}),
            lambda: api.remove("users", {}),
            lambda: api.remove("users", [("id", 1)]),
        )
        for index, operation in enumerate(invalid_calls):
            with self.subTest(operation=index), self.assertRaises(ValueError):
                operation()

    def test_user_identity_is_unique_and_provider_claims_are_paired(self):
        """Keep usernames and complete OIDC identities unique."""
        self.insert_row("users", username="Alice", auth_issuer="issuer", auth_subject="123")
        for fields in (
            {"username": "alice"},
            {"username": "Other", "auth_issuer": "issuer", "auth_subject": "123"},
            {"username": "Incomplete", "auth_subject": "123"},
            {"username": "Incomplete", "auth_issuer": "issuer"},
        ):
            with self.subTest(fields=fields), self.assertRaises(sqlite3.IntegrityError):
                self.insert_row("users", **fields)

    def test_fanta_manager_uniqueness_is_scoped_to_each_auction(self):
        """Allow each user to become a Fanta Manager once per auction."""
        first = self.make_auction("first")
        second = self.make_auction("second")
        guest_id = api.insert(
            "users",
            {"username": "Guest", "team_name": "Guest team"},
        )
        self.insert_row(
            "fanta_managers", auction_id=first["auction_id"], user_id=guest_id,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row(
                "fanta_managers",
                auction_id=first["auction_id"],
                user_id=guest_id,
            )
        self.insert_row(
            "fanta_managers", auction_id=second["auction_id"], user_id=guest_id,
        )

    def test_foreign_keys_are_enabled_for_every_write(self):
        """Reject Fanta Managers that reference missing auctions or users."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("fanta_managers", auction_id=999, user_id=999)
        fixture = self.make_auction("valid")
        with self.assertRaises(sqlite3.IntegrityError):
            api.update(
                "fanta_managers",
                {"user_id": 999},
                {"id": fixture["fanta_manager_id"]},
            )

    def test_cross_auction_references_are_rejected(self):
        """Keep purchases inside one auction."""
        first = self.make_auction("first")
        second = self.make_auction("second")
        invalid_rows = (
            ("purchases", {
                "auction_id": first["auction_id"],
                "fanta_manager_id": second["fanta_manager_id"],
                "player_id": first["player_id"], "price": 5,
            }),
            ("purchases", {
                "auction_id": first["auction_id"],
                "fanta_manager_id": first["fanta_manager_id"],
                "player_id": second["player_id"], "price": 5,
            }),
        )
        for table, fields in invalid_rows:
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.insert_row(table, **fields)

    def test_purchase_stores_only_final_owner_and_positive_price(self):
        """Persist one positive final purchase for each player and auction."""
        fixture = self.make_auction("purchases")
        fields = {
            "auction_id": fixture["auction_id"],
            "fanta_manager_id": fixture["fanta_manager_id"],
            "player_id": fixture["player_id"],
        }
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("purchases", **fields, price=0)
        self.insert_row("purchases", **fields, price=10)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row("purchases", **fields, price=20)

    def test_join_projects_and_filters_related_tables(self):
        """Join an ordered foreign-key chain with qualified columns."""
        fixture = self.make_auction("joined")
        self.insert_row(
            "purchases",
            auction_id=fixture["auction_id"],
            player_id=fixture["player_id"],
            fanta_manager_id=fixture["fanta_manager_id"],
            price=12,
        )

        manager_rows = api.join(
            ["users", "fanta_managers", "auctions"],
            {"auctions.id": fixture["auction_id"]},
            ["users.username", "users.team_name", "auctions.name"],
        )
        self.assertEqual(
            manager_rows,
            [{
                "users.username": "host_joined",
                "users.team_name": "Team host_joined",
                "auctions.name": "joined",
            }],
        )

        purchase_rows = api.join(
            ["players", "purchases", "fanta_managers", "users"],
            {"fanta_managers.id": fixture["fanta_manager_id"]},
            ["players.player", "purchases.price", "users.team_name"],
        )
        self.assertEqual(purchase_rows[0]["purchases.price"], 12)
        self.assertEqual(purchase_rows[0]["players.player"], "Example player")

    def test_join_rejects_ambiguous_or_unrelated_columns_and_tables(self):
        """Reject joins whose table path or column references are ambiguous."""
        self.make_auction("invalid-join")
        invalid_calls = (
            lambda: api.join(
                ["users", "fanta_managers"],
                {},
                ["id"],
            ),
            lambda: api.join(
                ["users", "fanta_managers"],
                {"id": 1},
                ["users.username"],
            ),
            lambda: api.join(
                ["users", "players"],
                {},
                ["users.username"],
            ),
        )
        for index, operation in enumerate(invalid_calls):
            with self.subTest(operation=index), self.assertRaises(ValueError):
                operation()

    def test_settings_are_persisted(self):
        """Store one typed setting per Fanta Manager and key."""
        fixture = self.make_auction("selection")
        key = "settings_A_budget_limit_widget_key"
        setting_id = self.insert_row(
            "settings", fanta_manager_id=fixture["fanta_manager_id"],
            key=key, value_json="150",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_row(
                "settings", fanta_manager_id=fixture["fanta_manager_id"],
                key=key, value_json="200",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            api.update(
                "settings",
                {"value_json": "not JSON"},
                {"id": setting_id},
            )

    def test_transactions_commit_as_a_unit_and_roll_back_on_failure(self):
        """Commit successful groups and roll back every row after a failure."""
        with api.transaction() as connection:
            self.insert_row("users", username="Committed", connection=connection)
            self.assertEqual(len(api.get("users", connection=connection)), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            with api.transaction() as connection:
                self.insert_row("users", username="Rolled back", connection=connection)
                self.insert_row("users", username="Committed", connection=connection)
        self.assertEqual(api.get("users", {"username": "Rolled back"}), [])

    def test_remove_protects_purchases_and_cascades_personal_data(self):
        """Protect purchase history and cascade settings on removal."""
        fixture = self.make_auction("removal")
        fanta_manager_id = fixture["fanta_manager_id"]
        self.insert_row(
            "settings", fanta_manager_id=fanta_manager_id,
            key="settings_A_budget_limit_widget_key", value_json="150",
        )
        purchase_id = self.insert_row(
            "purchases", auction_id=fixture["auction_id"],
            fanta_manager_id=fanta_manager_id, player_id=fixture["player_id"], price=5,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            api.remove("fanta_managers", {"id": fanta_manager_id})
        self.assertEqual(api.remove("purchases", {"id": purchase_id}), 1)
        self.assertEqual(api.remove("fanta_managers", {"id": fanta_manager_id}), 1)
        self.assertEqual(api.get("settings", {"fanta_manager_id": fanta_manager_id}), [])

    def test_failed_multirow_update_does_not_partially_modify_users(self):
        """Roll back every row when one update violates a uniqueness constraint."""
        api.insert("users", {"username": "First", "team_name": "First team"})
        api.insert("users", {"username": "Second", "team_name": "Second team"})
        with self.assertRaises(sqlite3.IntegrityError):
            api.update(
                "users",
                {"username": "Duplicate"},
                {"auth_subject": None},
            )
        self.assertEqual(
            {row["username"] for row in api.get("users")},
            {"First", "Second"},
        )

    def test_concurrent_duplicate_registration_has_one_winner(self):
        """Serialize concurrent duplicate inserts so exactly one succeeds."""
        barrier = threading.Barrier(2)

        def register():
            """Insert one shared username after both worker threads are ready."""
            barrier.wait(timeout=5)
            try:
                api.insert(
                    "users",
                    {"username": "Concurrent guest", "team_name": "Concurrent team"},
                )
            except sqlite3.IntegrityError:
                return "duplicate"
            return "inserted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(register) for _ in range(2)]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(outcomes, ["inserted", "duplicate"])


if __name__ == "__main__":
    unittest.main()
