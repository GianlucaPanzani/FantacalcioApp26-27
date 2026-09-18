"""Exercise the table-specific database modules with one related fixture."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.backend import db_api
from src.backend.auctions_db import (
    get_auction,
    get_auctions,
    set_auction,
    update_auction,
)
from src.backend.players_db import (
    get_player,
    get_players,
    set_player,
    update_player,
)
from src.backend.purchases_db import (
    get_purchase,
    get_purchases,
    set_purchase,
    update_purchase,
)
from src.backend.settings_db import (
    get_setting,
    get_settings,
    set_setting,
    update_setting,
)
from src.backend.users_db import set_user, update_user


class TableDatabaseModulesTests(unittest.TestCase):
    def setUp(self):
        """Create an isolated temporary database for each test."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = patch.object(
            db_api,
            "DB_PATH",
            Path(directory.name) / "table-modules.sqlite3",
        )
        database.start()
        self.addCleanup(database.stop)
        db_api.create_db()

    def test_table_modules_get_set_and_update_rows(self):
        """Use dictionary inserts and identifier-based updates for each table."""
        user = set_user({"username": "Host", "team_name": "Host FC"})
        auction = set_auction({
            "name": "Test auction",
            "season": "2026-27",
            "host_user_id": user["id"],
            "invite_code_hash": hashlib.sha256(b"invite").hexdigest(),
        })
        user = update_user(user["id"], {"auction_id": auction["id"]})
        player = set_player({
            "auction_id": auction["id"],
            "source_id": "10",
            "player": "Example player",
            "team": "Old club",
            "fanta_role": "A",
            "mantra_role": "Pc",
        })
        purchase = set_purchase({
            "auction_id": auction["id"],
            "player_id": player["id"],
            "user_id": user["id"],
            "price": 10,
        })
        setting = set_setting({
            "user_id": user["id"],
            "key": "example",
            "value_json": "true",
        })

        self.assertEqual(get_auction(auction["id"]), auction)
        self.assertEqual(get_auctions({"host_user_id": user["id"]}), [auction])
        self.assertEqual(
            update_auction(
                auction["id"],
                {"player_extraction_order": "alphabetic_order"},
            )["player_extraction_order"],
            "alphabetic_order",
        )

        self.assertEqual(get_player(player["id"]), player)
        self.assertEqual(get_players({"auction_id": auction["id"]}), [player])
        self.assertEqual(
            update_player(player["id"], {"team": "New club"})["team"],
            "New club",
        )

        self.assertEqual(get_purchase(purchase["id"]), purchase)
        self.assertEqual(
            get_purchases({"user_id": user["id"]}),
            [purchase],
        )
        self.assertEqual(
            update_purchase(purchase["id"], {"price": 15})["price"],
            15,
        )

        self.assertEqual(get_setting(setting["id"]), setting)
        self.assertEqual(
            get_settings({"user_id": user["id"]}),
            [setting],
        )
        self.assertEqual(
            update_setting(setting["id"], {"value_json": "false"})[
                "value_json"
            ],
            "false",
        )


if __name__ == "__main__":
    unittest.main()
