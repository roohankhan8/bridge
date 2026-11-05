import unittest

from app.db.session import _with_default_connect_timeout


class DatabaseSessionTests(unittest.TestCase):
    def test_postgresql_connection_timeout_defaults_to_five_seconds(self):
        url = _with_default_connect_timeout("postgresql+psycopg://user:pass@localhost/db")

        self.assertEqual(url.query["connect_timeout"], "5")

    def test_explicit_postgresql_connection_timeout_is_preserved(self):
        url = _with_default_connect_timeout(
            "postgresql+psycopg://user:pass@localhost/db?connect_timeout=12"
        )

        self.assertEqual(url.query["connect_timeout"], "12")

    def test_sqlite_url_is_unchanged(self):
        url = _with_default_connect_timeout("sqlite:///test.db")

        self.assertEqual(str(url), "sqlite:///test.db")


if __name__ == "__main__":
    unittest.main()
