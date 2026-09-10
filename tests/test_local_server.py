from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from local_server import ContactStore, validate_contact


class LocalContactTests(unittest.TestCase):
    def test_validation_and_storage(self) -> None:
        errors, data = validate_contact(
            {
                "name": "Test User",
                "email": "test@example.com",
                "subject": "Hello",
                "message": "A local test",
            }
        )
        self.assertEqual(errors, {})

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contacts.db"
            submission_id = ContactStore(path).add(data)
            with sqlite3.connect(path) as conn:
                row = conn.execute(
                    "SELECT id, email FROM submissions"
                ).fetchone()
            self.assertEqual(row, (submission_id, "test@example.com"))

    def test_invalid_email(self) -> None:
        errors, _ = validate_contact(
            {
                "name": "Test",
                "email": "invalid",
                "subject": "Hello",
                "message": "Message",
            }
        )
        self.assertIn("email", errors)


if __name__ == "__main__":
    unittest.main()
