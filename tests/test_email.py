import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.core.config import Settings
from app.core.email import send_auth_email


class AuthEmailTests(unittest.TestCase):
    def test_mailpit_sends_without_tls_or_auth(self):
        settings = Settings(
            smtp_host="127.0.0.1",
            smtp_port=1025,
            smtp_use_tls=False,
            smtp_from_email="dev@example.com",
        )
        smtp = MagicMock()
        smtp_context = smtp.__enter__.return_value

        with patch("app.core.email.smtplib.SMTP", return_value=smtp) as smtp_factory:
            send_auth_email(settings, "student@example.com", "Verify", "http://localhost/token")

        smtp_factory.assert_called_once_with("127.0.0.1", 1025, timeout=10)
        smtp_context.starttls.assert_not_called()
        smtp_context.login.assert_not_called()
        smtp_context.send_message.assert_called_once()

    def test_starttls_remains_enabled_by_default(self):
        settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_from_email="dev@example.com")
        smtp = MagicMock()
        smtp_context = smtp.__enter__.return_value

        with patch("app.core.email.smtplib.SMTP", return_value=smtp):
            send_auth_email(settings, "student@example.com", "Verify", "https://example.com/token")

        smtp_context.starttls.assert_called_once()

    def test_plaintext_smtp_auth_is_rejected(self):
        settings = Settings(
            smtp_host="127.0.0.1",
            smtp_port=1025,
            smtp_use_tls=False,
            smtp_username="user",
            smtp_password="password",
            smtp_from_email="dev@example.com",
        )

        with patch("app.core.email.smtplib.SMTP") as smtp_factory:
            with self.assertRaises(HTTPException) as error:
                send_auth_email(settings, "student@example.com", "Verify", "http://localhost/token")

        self.assertEqual(error.exception.status_code, 503)
        smtp_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
