"""Weekly audit: creates one Timesheet Compliance Audit per employee for a week."""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from aerele_timesheet_social_contract.compliance import (
	AUDIT_DOCTYPE,
	WeekContext,
	get_employees_for_week,
	get_excluded_employees,
	get_latest_auditable_week_end,
	get_settings,
)


def run_weekly_audit():
	"""Scheduler entry point (every Sunday): audits the latest week whose deadlines have passed."""
	settings = get_settings()
	if not cint(settings.enabled):
		return

	week_end = get_latest_auditable_week_end(settings)
	if week_end < getdate(settings.effective_from):
		return

	create_audits_for_week(week_end - timedelta(days=6))


def create_audits_for_week(week_start, posting_date=None) -> dict:
	"""Creates (and, if configured, submits) audits for every employee without one for the week.

	Each employee is handled inside its own savepoint, so one failure (for example a missing
	Salary Structure Assignment) does not stop the others. Failures go to the Error Log.
	"""
	settings = get_settings()
	week_start = getdate(week_start)
	week_end = week_start + timedelta(days=6)
	posting_date = getdate(posting_date or nowdate())

	already_audited = set(
		frappe.get_all(
			AUDIT_DOCTYPE,
			filters={"week_start": week_start, "docstatus": ["<", 2]},
			pluck="employee",
		)
	)
	employees = [
		e
		for e in get_employees_for_week(
			settings.company, week_start, week_end, get_excluded_employees(settings)
		)
		if e.name not in already_audited
	]
	if not employees:
		return {"created": 0, "failed": 0}

	context = WeekContext(settings, week_start, employees)
	created = failed = 0
	for employee in employees:
		savepoint = f"tsca_{frappe.scrub(employee.name)}"
		frappe.db.savepoint(savepoint)
		try:
			audit = frappe.new_doc(AUDIT_DOCTYPE)
			audit.update({"employee": employee.name, "week_start": week_start, "posting_date": posting_date})
			audit.flags.week_context = context
			audit.flags.ignore_permissions = True
			audit.insert()
			if cint(settings.auto_submit_audit):
				audit.submit()
			created += 1
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			failed += 1
			frappe.log_error(
				title=_("Timesheet compliance audit failed for {0}").format(employee.name),
				reference_doctype="Employee",
				reference_name=employee.name,
			)

	return {"created": created, "failed": failed}
