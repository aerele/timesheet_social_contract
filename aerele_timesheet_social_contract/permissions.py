"""Row-level access: employees see only their own audits and appeals."""

import frappe

from aerele_timesheet_social_contract.compliance import PANEL_ROLE

PRIVILEGED_ROLES = {PANEL_ROLE, "System Manager", "HR Manager", "Administrator"}


def _is_privileged(user: str) -> bool:
	return bool(PRIVILEGED_ROLES.intersection(frappe.get_roles(user)))


def _own_employees(user: str) -> list[str]:
	return frappe.get_all("Employee", filters={"user_id": user}, pluck="name")


def get_permission_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	if _is_privileged(user):
		return ""

	employees = _own_employees(user)
	if not employees:
		return "1=0"

	values = ", ".join(frappe.db.escape(e) for e in employees)
	return f"`tab{doctype}`.`employee` in ({values})"


def audit_query_conditions(user: str | None = None) -> str:
	return get_permission_query_conditions(user, "Timesheet Compliance Audit")


def appeal_query_conditions(user: str | None = None) -> str:
	return get_permission_query_conditions(user, "Timesheet Contribution Appeal")


def has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool | None:
	user = user or frappe.session.user
	if _is_privileged(user):
		return None
	if not doc.get("employee"):
		# A new appeal has no employee until its audit is set; the audit link is checked on save.
		return None if doc.is_new() else False
	return doc.employee in _own_employees(user)
