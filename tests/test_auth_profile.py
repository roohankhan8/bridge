import unittest
import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.api.v1.auth import (
    EmailRequest, EmailVerificationRequest, LoginRequest, PasswordResetRequest, RegisterRequest, StudentProfileInput,
    TokenRequest, create_auth_token, forgot_password, login, register, resend_verification, reset_password, verify_email,
)
from app.api.v1.me import (
    StudentProfilePatch, publish_student_profile, read_public_student_profile,
    read_public_student_profile_photo, read_student_profile_photo, update_student_profile,
    upload_student_photo,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import AuthToken, RefreshSession, StudentProfile, User


class AuthProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.settings = Settings(auth_jwt_secret="test-secret-that-is-at-least-32-bytes")
        self.profile = {
            "full_name": "Ayesha Khan", "key_skills": ["Python"], "experience_level": "intermediate",
            "availability_hours_per_week": 20,
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_registration_requires_verification_and_reset_revokes_sessions(self):
        emails = []
        with patch("app.api.v1.auth.send_auth_email", side_effect=lambda _s, _r, subject, body: emails.append((subject, body))):
            register(RegisterRequest(email="student@example.com", password="Password123!", student_profile=self.profile), db=self.db, settings=self.settings)
            user = self.db.query(User).one()
            with self.assertRaises(HTTPException):
                login(LoginRequest(email=user.email, password="Password123!"), db=self.db, settings=self.settings)
            verification_subject, verification_body = emails.pop()
            code = re.search(r"\b\d{8}\b", verification_body).group()
            self.assertEqual(verification_subject, "Verify your Bridge email")
            self.assertNotIn("http", verification_body)
            record = self.db.query(AuthToken).one()
            self.assertNotEqual(record.token_hash, code)
            verify_email(EmailVerificationRequest(email=user.email, code=code), db=self.db, settings=self.settings)
            with self.assertRaises(HTTPException):
                verify_email(EmailVerificationRequest(email=user.email, code=code), db=self.db, settings=self.settings)
            login(LoginRequest(email=user.email, password="Password123!"), db=self.db, settings=self.settings)
            self.assertTrue(self.db.query(RefreshSession).filter_by(user_id=user.id, revoked_at=None).count())

            forgot_password(EmailRequest(email=user.email), db=self.db, settings=self.settings)
            _, reset_body = emails.pop()
            self.assertIn("Reset your password using this link:", reset_body)
            reset_link = re.search(r"https?://\S+", reset_body).group()
            reset_token = parse_qs(urlparse(reset_link).query)["token"][0]
            reset_password(PasswordResetRequest(token=reset_token, password="NewPassword123!"), db=self.db)
            self.assertEqual(self.db.query(RefreshSession).filter_by(user_id=user.id, revoked_at=None).count(), 0)
            login(LoginRequest(email=user.email, password="NewPassword123!"), db=self.db, settings=self.settings)

    def test_verification_code_expires_after_ten_minutes(self):
        email_body = []
        with patch("app.api.v1.auth.send_auth_email", side_effect=lambda _s, _r, _sub, body: email_body.append(body)):
            register(RegisterRequest(email="expired@example.com", password="Password123!", student_profile=self.profile), db=self.db, settings=self.settings)
        user = self.db.query(User).one()
        code = re.search(r"\b\d{8}\b", email_body[0]).group()
        record = self.db.query(AuthToken).filter_by(user_id=user.id, purpose="verify_email").one()
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(HTTPException) as expired:
            verify_email(EmailVerificationRequest(email=user.email, code=code), db=self.db, settings=self.settings)
        self.assertEqual(expired.exception.status_code, 400)
        self.assertFalse(user.email_verified)

    def test_five_wrong_codes_lock_until_resend(self):
        email_bodies = []
        with patch("app.api.v1.auth.send_auth_email", side_effect=lambda _s, _r, _sub, body: email_bodies.append(body)):
            register(RegisterRequest(email="locked@example.com", password="Password123!", student_profile=self.profile), db=self.db, settings=self.settings)
            user = self.db.query(User).one()
            first_code = re.search(r"\b\d{8}\b", email_bodies[-1]).group()
            wrong_code = "00000000" if first_code != "00000000" else "11111111"
            for _ in range(5):
                with self.assertRaises(HTTPException) as wrong:
                    verify_email(EmailVerificationRequest(email=user.email, code=wrong_code), db=self.db, settings=self.settings)
                self.assertEqual(wrong.exception.status_code, 400)
            record = self.db.query(AuthToken).filter_by(user_id=user.id, purpose="verify_email").one()
            self.assertEqual(record.failed_attempts, 5)
            with self.assertRaises(HTTPException):
                verify_email(EmailVerificationRequest(email=user.email, code=first_code), db=self.db, settings=self.settings)

            record.created_at = datetime.now(UTC) - timedelta(seconds=61)
            self.db.commit()
            response = resend_verification(EmailRequest(email=user.email), db=self.db, settings=self.settings)
            self.assertIn("If the account exists", response["message"])
            second_code = re.search(r"\b\d{8}\b", email_bodies[-1]).group()
            self.assertNotEqual(first_code, second_code)
            verify_email(EmailVerificationRequest(email=user.email, code=second_code), db=self.db, settings=self.settings)
            self.assertTrue(user.email_verified)

    def test_resend_uses_generic_response_and_has_cooldown(self):
        email_bodies = []
        with patch("app.api.v1.auth.send_auth_email", side_effect=lambda _s, _r, _sub, body: email_bodies.append(body)):
            register(RegisterRequest(email="cooldown@example.com", password="Password123!", student_profile=self.profile), db=self.db, settings=self.settings)
            user = self.db.query(User).one()
            response = resend_verification(EmailRequest(email=user.email), db=self.db, settings=self.settings)
            self.assertIn("If the account exists", response["message"])
            self.assertEqual(len(email_bodies), 1)
            absent = resend_verification(EmailRequest(email="absent@example.com"), db=self.db, settings=self.settings)
            self.assertEqual(absent["message"], response["message"])
            self.assertEqual(len(email_bodies), 1)

    def test_legacy_verification_link_is_still_accepted(self):
        with patch("app.api.v1.auth.send_auth_email"):
            register(RegisterRequest(email="legacy@example.com", password="Password123!", student_profile=self.profile), db=self.db, settings=self.settings)
        user = self.db.query(User).one()
        token = create_auth_token(self.db, user, "verify_email")
        verify_email(EmailVerificationRequest(token=token), db=self.db, settings=self.settings)
        self.assertTrue(user.email_verified)

    def test_student_profile_validates_core_skill_limit_and_options(self):
        with self.assertRaises(ValidationError):
            StudentProfileInput(**self.profile, core_skills=[
                {"name": "Python", "depth": "advanced"}, {"name": "SQL", "depth": "beginner"},
                {"name": "Design", "depth": "intermediate"}, {"name": "Writing", "depth": "beginner"},
            ])
        with self.assertRaises(ValidationError):
            StudentProfileInput(**self.profile, availability="5-10")

    def test_registration_can_start_with_first_profile_step(self):
        step_one = {
            "full_name": "Ayesha Khan", "university": "Example University",
            "degree_program": "Computer Science", "graduation_year": 2027,
            "profile_photo_url": "https://example.com/photo.jpg",
        }
        request = RegisterRequest(email="draft@example.com", password="Password123!", student_profile=step_one)
        with patch("app.api.v1.auth.send_auth_email"):
            register(request, db=self.db, settings=self.settings)
        profile = self.db.query(StudentProfile).one()
        self.assertEqual(profile.full_name, "Ayesha Khan")
        self.assertIsNone(profile.experience_level)
        self.assertIsNone(profile.availability_hours_per_week)

    def test_registration_can_start_first_step_before_photo_upload(self):
        step_one = {
            "full_name": "Ayesha Khan", "university": "Example University",
            "degree_program": "Computer Science", "graduation_year": 2027,
        }
        request = RegisterRequest(email="photo-later@example.com", password="Password123!", student_profile=step_one)
        with patch("app.api.v1.auth.send_auth_email"):
            register(request, db=self.db, settings=self.settings)
        profile = self.db.query(StudentProfile).one()
        self.assertEqual(profile.full_name, "Ayesha Khan")
        self.assertIsNone(profile.profile_photo_url)

    def test_profile_steps_save_independently_and_publication_is_gated(self):
        user = User(email="profile@example.com", role="student", email_verified=False)
        self.db.add(user)
        self.db.flush()
        profile = StudentProfile(
            user_id=user.id, full_name="Ayesha Khan", key_skills=["Python"],
            experience_level="intermediate", availability_hours_per_week=20,
        )
        self.db.add(profile)
        self.db.commit()

        updated = update_student_profile(StudentProfilePatch(university="Example University"), user=user, db=self.db)
        self.assertEqual(updated.university, "Example University")
        self.assertEqual(updated.full_name, "Ayesha Khan")
        update_student_profile(
            StudentProfilePatch(core_skills=[{"name": "Python", "depth": "advanced"}]), user=user, db=self.db
        )
        with self.assertRaises(HTTPException):
            update_student_profile(StudentProfilePatch(supporting_skills=["python"]), user=user, db=self.db)
        self.assertEqual(self.db.get(StudentProfile, user.id).supporting_skills, [])
        with self.assertRaises(HTTPException):
            read_public_student_profile(user.id, db=self.db)
        with self.assertRaises(HTTPException):
            publish_student_profile(user=user, db=self.db)

        user.email_verified = True
        profile.degree_program = "Computer Science"
        profile.graduation_year = 2027
        profile.profile_photo_url = "https://example.com/photo.jpg"
        profile.highlights = "Built useful tools"
        profile.core_skills = [{"name": "Python", "depth": "advanced"}]
        profile.availability = "10-15"
        profile.preferred_work_types = ["paid_task"]
        profile.workplace_arrangement = "remote"
        profile.project_duration = "2-4"
        self.db.commit()
        publish_student_profile(user=user, db=self.db)
        public = read_public_student_profile(user.id, db=self.db)
        self.assertEqual(public.full_name, "Ayesha Khan")

    def test_student_photo_upload_stores_image_and_serves_it_to_owner_and_public_profile(self):
        with TemporaryDirectory() as upload_root:
            user = User(email="photo@example.com", role="student", email_verified=True)
            self.db.add(user)
            self.db.flush()
            profile = StudentProfile(
                user_id=user.id, full_name="Ayesha Khan", university="Example University",
                degree_program="Computer Science", graduation_year=2027,
                experience_level="intermediate", highlights="Built useful tools",
                core_skills=[{"name": "Python", "depth": "advanced"}],
                availability="10-15", preferred_work_types=["paid_task"],
                workplace_arrangement="remote", project_duration="2-4",
            )
            self.db.add(profile)
            self.db.commit()
            photo = UploadFile(
                filename="avatar.png", file=BytesIO(b"\x89PNG\r\n\x1a\nimage-bytes"),
                headers=Headers({"content-type": "image/png"}),
            )

            uploaded = upload_student_photo(photo, user=user, db=self.db, settings=Settings(profile_upload_dir=upload_root))

            saved = self.db.get(StudentProfile, user.id)
            photo_path = Path(upload_root) / "student_profiles" / saved.profile_photo_name
            self.assertTrue(photo_path.is_file())
            self.assertEqual(photo_path.read_bytes(), b"\x89PNG\r\n\x1a\nimage-bytes")
            self.assertTrue(uploaded.profile_photo_url.endswith("/me/student-profile/photo"))
            self.assertIsNone(saved.profile_photo_url)
            self.assertTrue(read_student_profile_photo(user=user, db=self.db, settings=Settings(profile_upload_dir=upload_root)).path)

            saved.published_at = datetime.now(UTC)
            self.db.commit()
            public_photo = read_public_student_profile_photo(user.id, db=self.db, settings=Settings(profile_upload_dir=upload_root))
            self.assertEqual(Path(public_photo.path), photo_path)

            user.email_verified = False
            self.db.commit()
            with self.assertRaises(HTTPException):
                read_public_student_profile_photo(user.id, db=self.db, settings=Settings(profile_upload_dir=upload_root))

    def test_student_photo_upload_rejects_invalid_or_oversized_images(self):
        user = User(email="invalid-photo@example.com", role="student")
        self.db.add(user)
        self.db.flush()
        profile = StudentProfile(user_id=user.id)
        self.db.add(profile)
        self.db.commit()
        with TemporaryDirectory() as upload_root:
            settings = Settings(profile_upload_dir=upload_root)
            invalid = UploadFile(
                filename="avatar.png", file=BytesIO(b"not an image"),
                headers=Headers({"content-type": "image/png"}),
            )
            with self.assertRaises(HTTPException) as invalid_response:
                upload_student_photo(invalid, user=user, db=self.db, settings=settings)
            self.assertEqual(invalid_response.exception.status_code, 415)

            oversized = UploadFile(
                filename="avatar.png", file=BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024)),
                headers=Headers({"content-type": "image/png"}),
            )
            with self.assertRaises(HTTPException) as oversized_response:
                upload_student_photo(oversized, user=user, db=self.db, settings=settings)
            self.assertEqual(oversized_response.exception.status_code, 413)
            self.assertFalse((Path(upload_root) / "student_profiles").exists())


if __name__ == "__main__":
    unittest.main()
