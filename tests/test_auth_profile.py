import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.auth import (
    EmailRequest, LoginRequest, PasswordResetRequest, RegisterRequest, StudentProfileInput,
    TokenRequest, forgot_password, login, register, reset_password, verify_email,
)
from app.api.v1.me import (
    StudentProfilePatch, publish_student_profile, read_public_student_profile,
    update_student_profile,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import RefreshSession, StudentProfile, User


class AuthProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.settings = Settings(auth_jwt_secret="test-secret")
        self.profile = {
            "full_name": "Ayesha Khan", "key_skills": ["Python"], "experience_level": "intermediate",
            "availability_hours_per_week": 20,
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_registration_requires_verification_and_reset_revokes_sessions(self):
        emails = []
        with patch("app.api.v1.auth.send_auth_email", side_effect=lambda _s, _r, _sub, link: emails.append(link)):
            register(RegisterRequest(email="student@example.com", password="Password123!", student_profile=self.profile), db=self.db, settings=self.settings)
            user = self.db.query(User).one()
            with self.assertRaises(HTTPException):
                login(LoginRequest(email=user.email, password="Password123!"), db=self.db, settings=self.settings)
            verify_email(TokenRequest(token=emails.pop().split("token=")[1]), db=self.db)
            login(LoginRequest(email=user.email, password="Password123!"), db=self.db, settings=self.settings)
            self.assertTrue(self.db.query(RefreshSession).filter_by(user_id=user.id, revoked_at=None).count())

            forgot_password(EmailRequest(email=user.email), db=self.db, settings=self.settings)
            reset_link = emails.pop()
            reset_password(PasswordResetRequest(token=reset_link.split("token=")[1], password="NewPassword123!"), db=self.db)
            self.assertEqual(self.db.query(RefreshSession).filter_by(user_id=user.id, revoked_at=None).count(), 0)
            login(LoginRequest(email=user.email, password="NewPassword123!"), db=self.db, settings=self.settings)

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


if __name__ == "__main__":
    unittest.main()
