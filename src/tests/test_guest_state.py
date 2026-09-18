"""Personal backups persist allowlisted DB state and selected players."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend import db_api
from backend.persistent_state_db import get_persistent_states, set_persistent_state
from backend.users_db import set_user
from lib.data_handler import export_guest_state, restore_guest_state


class GuestStateTests(unittest.TestCase):
    def setUp(self):
        """Create isolated users, persistent state and selection data."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        database_patch = patch.object(db_api, "DB_PATH", self.root / "state.sqlite3")
        database_patch.start()
        self.addCleanup(database_patch.stop)
        db_api.create_db()

        self.source_user = set_user({"username": "Guest", "team_name": "Guest FC"})
        self.target_user = set_user({"username": "Restored", "team_name": "Restored FC"})
        values = {
            "settings_my_manager_key": "Guest",
            "settings_P_budget_limit_widget_key": 40,
            "settings_P_graphical_cols_key": ["saves_per90", "clean_sheet_pct"],
            "settings_ai_enabled_key": True,
            "fantacalcio_fanta_role_widget_key": None,
        }
        for key, value in values.items():
            set_persistent_state({
                "user_id": self.source_user["id"],
                "page_name": key.split("_", 1)[0],
                "key": key,
                "value_json": json.dumps(value),
            })

        selection_path = Path(
            "data/csv/pages/selection/selection_selected_players_Guest.csv"
        )
        set_persistent_state({
            "user_id": self.source_user["id"],
            "page_name": "selection",
            "key": "selection_selected_players_csv_path_key",
            "value_json": json.dumps(selection_path.as_posix()),
        })
        (self.root / selection_path).parent.mkdir(parents=True)
        (self.root / selection_path).write_text(
            'Id,mln,interest,description\n123,12,Altissimo,"First line"\n',
            encoding="utf-8",
        )

    def make_archive(self, persistent_state=None, selection=None, extra=None, version=1):
        """Build a modified archive for validation tests."""
        payload = export_guest_state(self.source_user["id"], self.root)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        if persistent_state is not None:
            members["persistent_state.json"] = json.dumps(persistent_state)
        if selection is not None:
            members["selection_selected_players.csv"] = selection
        members["manifest.json"] = json.dumps({
            "format": "fantacalcio-persistent-state",
            "version": version,
        })
        if extra:
            members.update(extra)
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return result.getvalue()

    def test_roundtrip_restores_typed_state_and_selection(self):
        """Round-trip allowlisted values through DB-backed backup storage."""
        payload = export_guest_state(self.source_user["id"], self.root)
        result = restore_guest_state(
            payload,
            self.target_user["id"],
            "Restored",
            self.root,
        )

        self.assertEqual(result["selected_players"], 1)
        rows = get_persistent_states({"user_id": self.target_user["id"]})
        restored = {row["key"]: json.loads(row["value_json"]) for row in rows}
        self.assertEqual(restored["settings_P_budget_limit_widget_key"], 40)
        self.assertEqual(
            restored["settings_P_graphical_cols_key"],
            ["saves_per90", "clean_sheet_pct"],
        )
        self.assertIs(restored["settings_ai_enabled_key"], True)
        self.assertIsNone(restored["fantacalcio_fanta_role_widget_key"])
        restored_csv = self.root / restored["selection_selected_players_csv_path_key"]
        self.assertIn(b"123", restored_csv.read_bytes())

    def test_export_excludes_non_allowlisted_state(self):
        """Exclude private or official application state from the archive."""
        set_persistent_state({
            "user_id": self.source_user["id"],
            "page_name": "settings",
            "key": "settings_budget_widget_key",
            "value_json": "900",
        })
        payload = export_guest_state(self.source_user["id"], self.root)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            exported = json.loads(archive.read("persistent_state.json"))
        self.assertNotIn("settings_budget_widget_key", exported)

    def test_invalid_archive_does_not_change_persistent_state(self):
        """Reject malformed data before changing target state."""
        before = get_persistent_states({"user_id": self.target_user["id"]})
        invalid_archives = [
            self.make_archive(extra={"../../outside.txt": "bad"}),
            self.make_archive(
                persistent_state={"settings_P_budget_limit_widget_key": -1}
            ),
            self.make_archive(selection="Id,mln,interest,description\n1,-10,Basso,note\n"),
            self.make_archive(version=2),
            b"not a zip",
        ]
        for payload in invalid_archives:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(ValueError):
                    restore_guest_state(
                        payload,
                        self.target_user["id"],
                        "Restored",
                        self.root,
                    )
                self.assertEqual(
                    get_persistent_states({"user_id": self.target_user["id"]}),
                    before,
                )


if __name__ == "__main__":
    unittest.main()
