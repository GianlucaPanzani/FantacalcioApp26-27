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
from src.backend import db_api, users_db


class RegistrationPageTests(unittest.TestCase):
    def setUp(self):
        """Create an isolated database and load the registration page."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(
            patch.object(
                db_api,
                "DB_PATH",
                Path(directory.name) / "registration.sqlite3",
            )
        )
        self.enterContext(patch.dict(sys.modules, {
            "backend": backend,
            "backend.db_api": db_api,
            "backend.users_db": users_db,
        }))
        self.identity = SimpleNamespace(is_logged_in=True, iss="google", sub="guest-123")
        self.enterContext(patch.object(st, "user", self.identity))
        db_api.create_db()
        page = Path(__file__).resolve().parents[1] / "pages" / "registration.py"
        self.app = AppTest.from_file(str(page)).run()

    def submit(self, username="Guest", team_name="Guest FC"):
        """Submit the registration form with the supplied values."""
        self.app.text_input(key="registration_username_key").set_value(username)
        self.app.text_input(key="registration_team_name_key").set_value(team_name)
        self.app.button(key="registration_confirmation_button_key").click().run()
        self.assertFalse(self.app.exception)

    def test_submit_callback_reads_the_latest_username(self):
        """Store the current widget value when the form is submitted."""
        self.assertEqual(len(self.app.get("file_uploader")), 1)
        self.submit(username="Fresh username")
        users = users_db.get_users({
            "auth_issuer": "google",
            "auth_subject": "guest-123",
        })
        user = users[0]
        self.assertEqual(user["username"], "Fresh username")
        self.assertEqual(user["team_name"], "Guest FC")
        self.assertEqual(self.app.session_state["user_id"], user["id"])
        self.assertIn("successfully completed", self.app.success[0].value)

    def test_empty_username_shows_feedback_without_creating_user(self):
        """Show validation feedback without creating an empty user."""
        self.submit(username=" ")
        self.assertIn("Enter a username", self.app.error[0].value)
        self.assertEqual(
            users_db.get_users({"auth_issuer": "google", "auth_subject": "guest-123"}),
            [],
        )

    def test_empty_team_name_shows_feedback_without_creating_user(self):
        """Show validation feedback without creating a teamless user."""
        self.submit(team_name=" ")
        self.assertIn("Enter a team name", self.app.error[0].value)
        self.assertEqual(
            users_db.get_users({"auth_issuer": "google", "auth_subject": "guest-123"}),
            [],
        )

    def test_duplicate_username_shows_feedback(self):
        """Show feedback when the chosen username already exists."""
        users_db.set_user({
            "auth_issuer": "google",
            "auth_subject": "another-subject",
            "username": "Taken",
            "team_name": "Taken FC",
        })
        self.submit(username="taken")
        self.assertIn("already in use", self.app.error[0].value)
        self.assertEqual(
            users_db.get_users({"auth_issuer": "google", "auth_subject": "guest-123"}),
            [],
        )

    def test_page_requires_an_authenticated_identity(self):
        """Stop registration when no authenticated identity is available."""
        self.identity.is_logged_in = False
        self.app = self.app.run()
        self.assertIn("Sign in with Google", self.app.error[0].value)
        self.assertEqual(len(self.app.button), 0)


if __name__ == "__main__":
    unittest.main()
