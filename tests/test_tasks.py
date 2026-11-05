import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.tasks import (
    ApplicationDecision,
    ApplicationRequest,
    TaskCreate,
    apply_to_task,
    close_task,
    create_task,
    decide_application,
    list_applications,
    list_tasks,
    update_task,
    TaskUpdate,
)
from app.db.base import Base
from app.db.models import User


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.freelancer = User(email="freelancer@example.com", role="freelancer")
        self.student = User(email="student@example.com", role="student")
        self.other_freelancer = User(email="other@example.com", role="freelancer")
        self.db.add_all([self.freelancer, self.student, self.other_freelancer])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_open_task(self):
        return create_task(
            TaskCreate(
                title="Build a landing page",
                description="Create a responsive product page.",
                budget=Decimal("25000.00"),
                deadline=datetime.now(UTC).date() + timedelta(days=2),
                required_skills=["HTML", "CSS"],
            ),
            db=self.db,
            user=self.freelancer,
        )

    def test_student_can_apply_once_and_task_owner_can_accept(self):
        task = self.create_open_task()
        request = ApplicationRequest(proposal="I can deliver this in one week.")

        application = apply_to_task(task.id, request, db=self.db, user=self.student)
        self.assertEqual(application.status, "pending")
        accepted = decide_application(
            application.id,
            ApplicationDecision(status="accepted"),
            db=self.db,
            user=self.freelancer,
        )

        self.assertEqual(accepted.status, "accepted")

    def test_only_freelancers_can_create_and_students_can_apply(self):
        with self.assertRaises(HTTPException) as error:
            create_task(
                TaskCreate(
                    title="Build a landing page",
                    description="Create a responsive product page.",
                    budget=Decimal("25000.00"),
                    deadline=datetime.now(UTC).date() + timedelta(days=2),
                    required_skills=["HTML"],
                ),
                db=self.db,
                user=self.student,
            )
        self.assertEqual(error.exception.status_code, 403)

        task = self.create_open_task()
        with self.assertRaises(HTTPException) as error:
            apply_to_task(
                task.id,
                ApplicationRequest(proposal="I can deliver this in one week."),
                db=self.db,
                user=self.freelancer,
            )
        self.assertEqual(error.exception.status_code, 403)

    def test_task_validation_rejects_invalid_budget_skills_and_past_deadline(self):
        with self.assertRaises(ValidationError):
            TaskCreate(
                title="  ",
                description="Create a responsive product page.",
                budget=Decimal("25000"),
                deadline=datetime.now(UTC).date() + timedelta(days=2),
                required_skills=["HTML"],
            )
        with self.assertRaises(ValidationError):
            TaskCreate(
                title="Build a landing page",
                description="Create a responsive product page.",
                budget=Decimal("0"),
                deadline=datetime.now(UTC).date() + timedelta(days=2),
                required_skills=["HTML"],
            )
        with self.assertRaises(ValidationError):
            TaskCreate(
                title="Build a landing page",
                description="Create a responsive product page.",
                budget=Decimal("25000"),
                deadline=datetime.now(UTC).date() + timedelta(days=2),
                required_skills=["Python", "python"],
            )
        with self.assertRaises(ValidationError):
            TaskCreate(
                title="Build a landing page",
                description="Create a responsive product page.",
                budget=Decimal("25000"),
                deadline=datetime.now(UTC).date() - timedelta(days=1),
                required_skills=["HTML"],
            )

    def test_duplicate_application_is_rejected(self):
        task = self.create_open_task()
        request = ApplicationRequest(proposal="I can deliver this in one week.")
        apply_to_task(task.id, request, db=self.db, user=self.student)

        with self.assertRaises(HTTPException) as error:
            apply_to_task(task.id, request, db=self.db, user=self.student)

        self.assertEqual(error.exception.status_code, 409)

    def test_only_task_owner_can_close_task(self):
        task = self.create_open_task()

        with self.assertRaises(HTTPException) as error:
            close_task(task.id, db=self.db, user=self.other_freelancer)

        self.assertEqual(error.exception.status_code, 404)

    def test_owner_can_edit_and_close_task(self):
        task = self.create_open_task()
        updated = update_task(
            task.id,
            TaskUpdate(title="Updated landing page"),
            db=self.db,
            user=self.freelancer,
        )
        closed = close_task(task.id, db=self.db, user=self.freelancer)

        self.assertEqual(updated.title, "Updated landing page")
        self.assertEqual(closed.status, "closed")

    def test_closed_task_rejects_application(self):
        task = self.create_open_task()
        close_task(task.id, db=self.db, user=self.freelancer)

        with self.assertRaises(HTTPException) as error:
            apply_to_task(
                task.id,
                ApplicationRequest(proposal="I can deliver this in one week."),
                db=self.db,
                user=self.student,
            )

        self.assertEqual(error.exception.status_code, 409)

    def test_task_listing_uses_cursor_pages(self):
        self.create_open_task()
        self.create_open_task()

        first = list_tasks(cursor=None, limit=1, db=self.db, user=self.student)
        second = list_tasks(cursor=first.next_cursor, limit=1, db=self.db, user=self.student)

        self.assertEqual(len(first.items), 1)
        self.assertEqual(len(second.items), 1)
        self.assertNotEqual(first.items[0].id, second.items[0].id)

    def test_applications_are_rejected_after_deadline(self):
        task = self.create_open_task()
        task.deadline = datetime.now(UTC).date() - timedelta(days=1)
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            apply_to_task(
                task.id,
                ApplicationRequest(proposal="I can deliver this in one week."),
                db=self.db,
                user=self.student,
            )

        self.assertEqual(error.exception.status_code, 409)

    def test_non_owner_cannot_decide_an_application(self):
        task = self.create_open_task()
        application = apply_to_task(
            task.id,
            ApplicationRequest(proposal="I can deliver this in one week."),
            db=self.db,
            user=self.student,
        )

        with self.assertRaises(HTTPException) as error:
            decide_application(
                application.id,
                ApplicationDecision(status="rejected"),
                db=self.db,
                user=self.other_freelancer,
            )

        self.assertEqual(error.exception.status_code, 404)

    def test_only_task_owner_can_list_applications(self):
        task = self.create_open_task()
        application = apply_to_task(
            task.id,
            ApplicationRequest(proposal="I can deliver this in one week."),
            db=self.db,
            user=self.student,
        )

        with self.assertRaises(HTTPException) as error:
            list_applications(task.id, cursor=None, limit=20, db=self.db, user=self.other_freelancer)
        self.assertEqual(error.exception.status_code, 404)

        page = list_applications(task.id, cursor=None, limit=20, db=self.db, user=self.freelancer)
        self.assertEqual([item.id for item in page.items], [application.id])

    def test_task_owner_cannot_apply_to_own_task(self):
        task = self.create_open_task()
        self.freelancer.role = "student"
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            apply_to_task(
                task.id,
                ApplicationRequest(proposal="I can deliver this in one week."),
                db=self.db,
                user=self.freelancer,
            )
        self.assertEqual(error.exception.status_code, 409)

    def test_application_decision_cannot_be_changed(self):
        task = self.create_open_task()
        application = apply_to_task(
            task.id,
            ApplicationRequest(proposal="I can deliver this in one week."),
            db=self.db,
            user=self.student,
        )
        decide_application(
            application.id,
            ApplicationDecision(status="accepted"),
            db=self.db,
            user=self.freelancer,
        )

        with self.assertRaises(HTTPException) as error:
            decide_application(
                application.id,
                ApplicationDecision(status="rejected"),
                db=self.db,
                user=self.freelancer,
            )

        self.assertEqual(error.exception.status_code, 409)

    def test_stale_application_decision_cannot_overwrite_a_newer_decision(self):
        task = self.create_open_task()
        application = apply_to_task(
            task.id,
            ApplicationRequest(proposal="I can deliver this in one week."),
            db=self.db,
            user=self.student,
        )
        other_session = Session(self.engine)
        try:
            decide_application(
                application.id,
                ApplicationDecision(status="accepted"),
                db=other_session,
                user=self.freelancer,
            )
            with self.assertRaises(HTTPException) as error:
                decide_application(
                    application.id,
                    ApplicationDecision(status="rejected"),
                    db=self.db,
                    user=self.freelancer,
                )
        finally:
            other_session.close()

        self.assertEqual(error.exception.status_code, 409)

if __name__ == "__main__":
    unittest.main()
