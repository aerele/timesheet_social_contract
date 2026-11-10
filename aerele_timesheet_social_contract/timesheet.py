"""Timesheet doc events: record when each entry was submitted."""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from aerele_timesheet_social_contract.compliance import PANEL_ROLE

SUBMITTED_ON_FIELD = "sc_submitted_on"
ROW_KEY_FIELDS = (
	"from_time",
	"to_time",
	"hours",
	"activity_type",
	"project",
	"task",
	"is_billable",
	"description",
)


def row_key(row) -> tuple:
	"""Identity of a time log entry, used to spot entries carried over unchanged in an amendment."""
	return (
		get_datetime(row.get("from_time")),
		get_datetime(row.get("to_time")) if row.get("to_time") else None,
		flt(row.get("hours"), 4),
		row.get("activity_type") or "",
		row.get("project") or "",
		row.get("task") or "",
		cint(row.get("is_billable")),
		(row.get("description") or "").strip(),
	)


def get_inherited_stamps(original_rows) -> dict[tuple, list]:
	stamps: dict[tuple, list] = {}
	for row in original_rows:
		if row.get(SUBMITTED_ON_FIELD):
			stamps.setdefault(row_key(row), []).append(get_datetime(row.get(SUBMITTED_ON_FIELD)))
	for values in stamps.values():
		values.sort()
	return stamps


def stamp_rows(rows, original_rows, submitted_on) -> None:
	"""Entries carried over unchanged keep the original submission time; new or changed ones get `submitted_on`."""
	inherited = get_inherited_stamps(original_rows or [])
	for row in rows:
		stamps = inherited.get(row_key(row))
		setattr(row, SUBMITTED_ON_FIELD, stamps.pop(0) if stamps else submitted_on)


def before_submit(doc, method=None):
	original_rows = []
	if doc.amended_from:
		original_rows = frappe.get_all(
			"Timesheet Detail",
			filters={"parent": doc.amended_from, "parenttype": "Timesheet"},
			fields=[*ROW_KEY_FIELDS, SUBMITTED_ON_FIELD],
		)
	stamp_rows(doc.time_logs, original_rows, now_datetime())


def before_cancel(doc, method=None):
	"""Changes to an invoiced period need the panel's approval."""
	if any(row.sales_invoice for row in doc.time_logs) and PANEL_ROLE not in frappe.get_roles():
		frappe.throw(
			_("This timesheet is already invoiced. Only the Timesheet Panel can cancel it."),
			frappe.PermissionError,
		)
