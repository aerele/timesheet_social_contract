import frappe
from frappe import _
from frappe.utils import getdate

from aerele_timesheet_social_contract.compliance import (
	PANEL_ROLE,
	get_latest_auditable_week_end,
	get_settings,
)


@frappe.whitelist(methods=["POST"])
def run_audit_for_week(week_start: str) -> str:
	"""Queues the audit for one week. For the panel, e.g. to re-run a week after fixing data."""
	frappe.only_for([PANEL_ROLE, "System Manager"])

	settings = get_settings()
	week_start = getdate(week_start)
	if week_start.weekday() != 0:
		frappe.throw(_("Week Start must be a Monday."))
	if week_start > get_latest_auditable_week_end(settings):
		frappe.throw(_("This week's submission deadlines have not all passed yet."))

	frappe.enqueue(
		"aerele_timesheet_social_contract.audit.create_audits_for_week",
		queue="long",
		week_start=week_start,
		job_id=f"timesheet_social_contract_audit::{week_start}",
		deduplicate=True,
	)
	return _(
		"Audit for the week starting {0} is queued. Employees who already have an audit are skipped."
	).format(frappe.format_value(week_start, {"fieldtype": "Date"}))
