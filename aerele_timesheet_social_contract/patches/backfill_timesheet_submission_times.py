"""Fills `Submitted On` for timesheets submitted before this app recorded it.

Timesheet does not track changes on insider, so the real submission time is not stored anywhere.
Submitted timesheets use their last modified time; cancelled ones use their creation time (their
modified time is the cancellation). Entries carried over unchanged into an amendment inherit the
original entry's time, as they would going forward.
"""

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, getdate

from aerele_timesheet_social_contract.timesheet import (
	ROW_KEY_FIELDS,
	SUBMITTED_ON_FIELD,
	get_inherited_stamps,
	row_key,
)

# A week of margin before the effective date, for amendments of earlier timesheets.
DEFAULT_EFFECTIVE_FROM = "2026-11-01"


def execute():
	if not frappe.db.has_column("Timesheet Detail", SUBMITTED_ON_FIELD):
		return

	effective_from = (
		frappe.db.get_single_value("Timesheet Social Contract Settings", "effective_from")
		or DEFAULT_EFFECTIVE_FROM
	)
	since = getdate(effective_from) - timedelta(days=7)

	timesheets = frappe.get_all(
		"Timesheet",
		filters={"docstatus": ["in", [1, 2]], "end_date": [">=", since]},
		fields=["name", "docstatus", "amended_from", "creation", "modified"],
		order_by="creation asc",
	)
	if not timesheets:
		return

	names = [ts.name for ts in timesheets]
	rows = frappe.get_all(
		"Timesheet Detail",
		filters={"parenttype": "Timesheet", "parent": ["in", names]},
		fields=["name", "parent", *ROW_KEY_FIELDS, SUBMITTED_ON_FIELD],
	)
	rows_by_parent: dict[str, list] = {}
	for row in rows:
		rows_by_parent.setdefault(row.parent, []).append(row)

	updates = {}
	for ts in timesheets:
		fallback = get_datetime(ts.modified if ts.docstatus == 1 else ts.creation)
		inherited = get_inherited_stamps(rows_by_parent.get(ts.amended_from, []))
		for row in rows_by_parent.get(ts.name, []):
			if row.get(SUBMITTED_ON_FIELD):
				continue
			stamps = inherited.get(row_key(row))
			row[SUBMITTED_ON_FIELD] = stamps.pop(0) if stamps else fallback
			updates[row.name] = {SUBMITTED_ON_FIELD: row[SUBMITTED_ON_FIELD]}

	if updates:
		frappe.db.bulk_update("Timesheet Detail", updates, update_modified=False)
