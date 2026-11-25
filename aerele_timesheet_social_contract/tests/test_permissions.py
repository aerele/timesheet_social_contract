"""Row-level access for audits and appeals.

The has_permission hook can only deny: Frappe treats any falsy return, None included, as a denial.
Roles and employees are patched, so these tests need nothing in the database.
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from aerele_timesheet_social_contract.permissions import has_permission

USER = "member@example.com"


def make_doc(employee=None, is_new=False):
	return frappe._dict(employee=employee, is_new=lambda: is_new)


@patch("aerele_timesheet_social_contract.permissions._own_employees", return_value=["EMP-1"])
class TestHasPermission(UnitTestCase):
	def check(self, doc, roles=("Employee",)):
		with patch("frappe.get_roles", return_value=list(roles)):
			return has_permission(doc, "read", USER)

	def test_privileged_roles_are_not_blocked(self, _employees):
		for role in ("Timesheet Panel", "System Manager", "HR Manager"):
			with self.subTest(role=role):
				self.assertIs(self.check(make_doc("EMP-2"), roles=("Employee", role)), True)

	def test_own_record(self, _employees):
		self.assertIs(self.check(make_doc("EMP-1")), True)

	def test_someone_elses_record(self, _employees):
		self.assertIs(self.check(make_doc("EMP-2")), False)

	def test_new_appeal_before_the_audit_is_set(self, _employees):
		self.assertIs(self.check(make_doc(is_new=True)), True)

	def test_saved_record_without_employee(self, _employees):
		self.assertIs(self.check(make_doc()), False)
