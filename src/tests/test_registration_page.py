"""Exercise the Streamlit registration callback with a simulated Google identity."""

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from src import backend
from src.backend import api, user_services


class RegistrationPageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.object(api, "DB_PATH", Path(directory.name) / "registration.sqlite3"))
        self.enterContext(patch.dict(sys.modules, {
            "backend": backend,
            "backend.api": api,
            "backend.user_services": user_services,
        }))
        self.identity = SimpleNamespace(is_logged_in=True, iss="google", sub="guest-123")
        self.enterContext(patch.object(st, "user", self.identity))
        api.create()
        page = Path(__file__).resolve().parents[1] / "pages" / "registration.py"
        self.app = AppTest.from_file(str(page)).run()

    def submit(self, username="Guest", team_name="Guest FC"):
        self.app.text_input(key="registration_username_key").set_value(username)
        self.app.text_input(key="registration_team_name_key").set_value(team_name)
        self.app.button(key="registration_confirmation_button_key").click().run()
        self.assertFalse(self.app.exception)

    def test_submit_callback_reads_the_latest_username(self):
        self.assertEqual(len(self.app.get("file_uploader")), 1)
        self.submit(username="Fresh username")
        user = user_services.get_user("google", "guest-123")
        self.assertEqual(user["username"], "Fresh username")
        self.assertEqual(self.app.session_state["user_id"], user["id"])
        self.assertIn("successfully completed", self.app.success[0].value)

    def test_empty_username_shows_feedback_without_creating_user(self):
        self.submit(username=" ")
        self.assertIn("Enter a username", self.app.error[0].value)
        self.assertIsNone(user_services.get_user("google", "guest-123"))

    def test_duplicate_username_shows_feedback(self):
        user_services.set_user("google", "another-subject", "Taken")
        self.submit(username="taken")
        self.assertIn("already in use", self.app.error[0].value)
        self.assertIsNone(user_services.get_user("google", "guest-123"))

    def test_page_requires_an_authenticated_identity(self):
        self.identity.is_logged_in = False
        self.app = self.app.run()
        self.assertIn("Sign in with Google", self.app.error[0].value)
        self.assertEqual(len(self.app.button), 0)


if __name__ == "__main__":
    unittest.main()
