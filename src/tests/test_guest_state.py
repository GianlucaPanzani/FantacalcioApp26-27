"""Guest backups must never restore official auction state or credentials."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from src.lib.data_handler import export_guest_state, restore_guest_state


class GuestStateTests(unittest.TestCase):
    def setUp(self):
        """Create source and destination fixtures for guest backup tests."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "guest"
        self.target = Path(self.temporary.name) / "restored"
        self.source.mkdir()
        self.target.mkdir()
        self.selection = Path("data/csv/pages/selection/selection_selected_players.csv")
        (self.source / ".env").write_text(
            "settings_my_manager_key=Guest\nsettings_my_manager_key_type=str\n"
            "settings_P_budget_limit_widget_key=40\nsettings_P_budget_limit_widget_key_type=int\n"
            "settings_P_graphical_cols_key=saves_per90,clean_sheet_pct\n"
            "settings_P_graphical_cols_key_type=list\n"
            "settings_ai_enabled_key=true\nsettings_ai_enabled_key_type=bool\n"
            "selection_R_widget_key=P\nselection_R_widget_key_type=str\n"
            "fantacalcio_fanta_role_widget_key=\nfantacalcio_fanta_role_widget_key_type=NoneType\n"
            "settings_budget_widget_key=900\nsettings_budget_widget_key_type=int\n"
            "settings_managers_key=Guest,Other\nsettings_managers_key_type=list\n"
            "settings_D_limit_widget_key=20\nsettings_D_limit_widget_key_type=int\n"
            "settings_defender_modifier_enabled_key=true\n"
            "HF_TOKEN=source-private-token\n"
            "fantacalcio_bought_players_df_key=private-purchases.csv\n"
            "fantacalcio_bought_players_df_key_type=pd.DataFrame\n",
            encoding="utf-8",
        )
        (self.source / self.selection).parent.mkdir(parents=True)
        (self.source / self.selection).write_text(
            'Id,mln,interest,description\n123,12,Altissimo,"First line\nsecond, line"\n',
            encoding="utf-8",
        )
        self.existing_env = (
            "# Existing host configuration\nHF_TOKEN=target-private-token\n"
            "settings_budget_widget_key=500\nsettings_budget_widget_key_type=int\n"
            "settings_managers_key=Host,Existing\nsettings_managers_key_type=list\n"
            "settings_D_limit_widget_key=8\nsettings_D_limit_widget_key_type=int\n"
            "selection_selected_999_key=true\nselection_selected_999_key_type=bool\n"
            "selection_selection_players_restored_v2_key=true\n"
        )
        (self.target / ".env").write_text(self.existing_env, encoding="utf-8")
        (self.target / self.selection).parent.mkdir(parents=True)
        (self.target / self.selection).write_bytes(b"Id,mln,interest,description\n999,1,Basso,Old\n")
        self.purchased_paths = [
            self.target / "data/csv/pages/fantacalcio/fantacalcio_bought_players.csv",
            self.target / "data/csv/pages/settings/settings_fantacalcio_bought_players.csv",
        ]
        for path in self.purchased_paths:
            path.parent.mkdir(parents=True)
            path.write_bytes(b"id,manager,mln\n900,Host,30\n")

    def make_archive(self, settings=None, selection=None, extra=None, version=1):
        """Build a modified backup archive for validation tests."""
        payload = export_guest_state(self.source)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        if settings is not None:
            members["personal.env"] = settings
        if selection is not None:
            members["selection_selected_players.csv"] = selection
        members["manifest.json"] = json.dumps({"format": "fantacalcio-guest-state", "version": version})
        if extra:
            members.update(extra)
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return result.getvalue()

    def test_roundtrip_preserves_shared_state_and_typed_preferences(self):
        """Round-trip allowed personal state without copying private host data."""
        payload = export_guest_state(self.source)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            exported = archive.read("personal.env").decode()
            for forbidden in ("HF_TOKEN", "settings_managers", "settings_budget_widget_key", "bought_players", "settings_D_limit", "modifier"):
                self.assertNotIn(forbidden, exported)
        result = restore_guest_state(io.BytesIO(payload), self.target)
        self.assertEqual(result["selected_players"], 1)
        self.assertEqual(result["settings"]["settings_P_budget_limit_widget_key"], 40)
        self.assertEqual(result["settings"]["settings_P_graphical_cols_key"], ["saves_per90", "clean_sheet_pct"])
        self.assertIs(result["settings"]["settings_ai_enabled_key"], True)
        self.assertIsNone(result["settings"]["fantacalcio_fanta_role_widget_key"])
        restored = (self.target / ".env").read_text()
        self.assertIn("HF_TOKEN=target-private-token", restored)
        self.assertIn("settings_budget_widget_key=500", restored)
        self.assertIn("settings_D_limit_widget_key=8", restored)
        self.assertIn("settings_managers_key=Host,Existing", restored)
        self.assertNotIn("selection_selected_999_key", restored)
        self.assertNotIn("restored_v2_key", restored)
        self.assertEqual((self.target / self.selection).read_bytes(), (self.source / self.selection).read_bytes())
        for path in self.purchased_paths:
            self.assertEqual(path.read_bytes(), b"id,manager,mln\n900,Host,30\n")
        # A restored state remains exportable using the app's existing types.
        self.assertIsInstance(export_guest_state(self.target), bytes)

    def test_rejects_invalid_archives_before_writing(self):
        """Reject unsafe archive data before changing either destination file."""
        env_before = (self.target / ".env").read_bytes()
        csv_before = (self.target / self.selection).read_bytes()
        invalid_archives = [
            self.make_archive(extra={"../../outside.txt": "bad"}),
            self.make_archive(settings="settings_budget_widget_key=999\nsettings_budget_widget_key_type=int\n"),
            self.make_archive(settings="settings_P_budget_limit_widget_key=-1\nsettings_P_budget_limit_widget_key_type=int\n"),
            self.make_archive(settings="statistics_number_of_players_key=5\nstatistics_number_of_players_key_type=int\n"),
            self.make_archive(settings="statistics_seasons_to_plot_key=11\nstatistics_seasons_to_plot_key_type=int\n"),
            self.make_archive(settings="fantacalcio_fanta_managers_split_value_widget_key=6\nfantacalcio_fanta_managers_split_value_widget_key_type=int\n"),
            self.make_archive(settings="settings_ai_enabled_key=path.csv\nsettings_ai_enabled_key_type=pd.DataFrame\n"),
            self.make_archive(selection="Id,mln,interest,description\n1,-10,Basso,note\n"),
            self.make_archive(selection="Id,mln,interest,description\n1,1,Basso,a\n1,2,Alto,b\n"),
            self.make_archive(selection="Id,mln,interest,description,manager\n1,1,Basso,note,Other\n"),
            self.make_archive(version=2),
            b"not a zip",
        ]
        for payload in invalid_archives:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(ValueError):
                    restore_guest_state(payload, self.target)
                self.assertEqual((self.target / ".env").read_bytes(), env_before)
                self.assertEqual((self.target / self.selection).read_bytes(), csv_before)

    def test_restore_rolls_back_first_file_if_second_replace_fails(self):
        """Restore the first file when replacing the second file fails."""
        env_before = (self.target / ".env").read_bytes()
        csv_before = (self.target / self.selection).read_bytes()
        real_replace = os.replace

        def fail_selection(source, target):
            """Simulate a failure while replacing the shortlist file."""
            if target == (self.target / self.selection).resolve():
                raise OSError("Simulated write failure")
            return real_replace(source, target)

        with patch("src.lib.data_handler.os.replace", side_effect=fail_selection):
            with self.assertRaises(OSError):
                restore_guest_state(export_guest_state(self.source), self.target)
        self.assertEqual((self.target / ".env").read_bytes(), env_before)
        self.assertEqual((self.target / self.selection).read_bytes(), csv_before)

    def test_missing_local_state_exports_an_empty_shortlist(self):
        """Export a valid empty shortlist when no local state exists."""
        empty = Path(self.temporary.name) / "empty"
        report = restore_guest_state(export_guest_state(empty), self.target)
        self.assertEqual(report, {"settings": {}, "selected_players": 0})
        self.assertEqual((self.target / self.selection).read_bytes(), b"Id,mln,interest,description\n")

    def test_restore_uses_only_the_local_shortlist_path(self):
        """Ignore imported paths and use the destination's configured path."""
        custom = "data/personal/shortlist.csv"
        with (self.target / ".env").open("a") as env:
            env.write(f"selection_selected_players_csv_path_key={custom}\n")
        restore_guest_state(export_guest_state(self.source), self.target)
        self.assertTrue((self.target / custom).exists())
        self.assertIn(custom, (self.target / ".env").read_text())
        self.assertIn(b"999", (self.target / self.selection).read_bytes())


if __name__ == "__main__":
    unittest.main()
