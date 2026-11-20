"""Unit tests for external-certification access and migrated-password login (no DB / network).

Run from the backend root:  python -m unittest tests.test_external_certifications_access -v
"""

import unittest
from types import SimpleNamespace as NS

import bcrypt
from fastapi import HTTPException

from app.services import auth_service
from app.services.role_access_service import (
    can_edit_external_certifications,
    can_view_external_certifications,
)


def user(*role_names, password=None):
    return NS(
        id=1,
        email="user328@example.com",
        password=password,
        roles=[NS(role=NS(name=name)) for name in role_names],
    )


class FakeDb:
    def __init__(self, found):
        self.found = found
        self.commits = 0

    def query(self, _model):
        return self

    def filter(self, *_args):
        return self

    def first(self):
        return self.found

    def commit(self):
        self.commits += 1


class CertificationAccessTests(unittest.TestCase):
    def test_viewer_can_view_but_not_edit(self):
        u = user("certification_viewer")
        self.assertTrue(can_view_external_certifications(u))
        self.assertFalse(can_edit_external_certifications(u))

    def test_editor_can_view_and_edit(self):
        u = user("certification_editor")
        self.assertTrue(can_view_external_certifications(u))
        self.assertTrue(can_edit_external_certifications(u))

    def test_admin_has_full_access(self):
        u = user("admin")
        self.assertTrue(can_view_external_certifications(u))
        self.assertTrue(can_edit_external_certifications(u))

    def test_audit_roles_alone_grant_no_access(self):
        u = user("auditor", "quality_manager", "top_management", "editor")
        self.assertFalse(can_view_external_certifications(u))
        self.assertFalse(can_edit_external_certifications(u))


class LegacyBcryptLoginTests(unittest.TestCase):
    def setUp(self):
        self.legacy_hash = bcrypt.hashpw(b"current-password", bcrypt.gensalt()).decode()

    def test_correct_password_logs_in_and_upgrades_hash_to_argon2(self):
        u = user("certification_viewer", password=self.legacy_hash)
        db = FakeDb(u)
        result = auth_service.authenticate_user(NS(email=u.email, password="current-password"), db)
        self.assertIs(result, u)
        self.assertTrue(u.password.startswith("$argon2"))
        self.assertTrue(auth_service.bcrypt_context.verify("current-password", u.password))
        self.assertEqual(db.commits, 1)

    def test_wrong_password_is_rejected_and_hash_kept(self):
        u = user("certification_viewer", password=self.legacy_hash)
        db = FakeDb(u)
        with self.assertRaises(HTTPException) as ctx:
            auth_service.authenticate_user(NS(email=u.email, password="wrong"), db)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(u.password, self.legacy_hash)
        self.assertEqual(db.commits, 0)

    def test_argon2_accounts_are_unaffected(self):
        u = user("auditor", password=auth_service.bcrypt_context.hash("pw"))
        original = u.password
        db = FakeDb(u)
        self.assertIs(auth_service.authenticate_user(NS(email=u.email, password="pw"), db), u)
        self.assertEqual(u.password, original)
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
