# Copyright (c) 2026, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, getdate, nowdate

from aerele_timesheet_social_contract.compliance import AUDIT_DOCTYPE, get_settings

ACCEPT = "Accept"
REJECT = "Reject"


class TimesheetContributionAppeal(Document):
	def validate(self):
		self.validate_audit()
		if self.is_new():
			self.validate_appeal_window()
		self.validate_votes()
		self.set_decision()

	def before_submit(self):
		if not self.decision:
			frappe.throw(
				_("The panel needs at least {0} matching votes before this appeal can be submitted.").format(
					cint(get_settings().votes_required)
				)
			)

	def on_submit(self):
		if self.decision == "Accepted":
			audit = frappe.get_doc(AUDIT_DOCTYPE, self.audit)
			if audit.docstatus == 1:
				# Cancelling reverses the contribution: the Additional Salary is cancelled, or
				# refunded in the next payroll if it was already deducted.
				audit.flags.ignore_permissions = True
				audit.add_comment(
					"Info", _("Cancelled after appeal {0} was accepted by the panel.").format(self.name)
				)
				audit.cancel()

	def validate_audit(self):
		audit = frappe.db.get_value(
			AUDIT_DOCTYPE, self.audit, ["docstatus", "employee", "posting_date"], as_dict=True
		)
		if not audit or audit.docstatus != 1:
			frappe.throw(_("An appeal can be raised only against a submitted audit."))

		self.employee = audit.employee
		if not frappe.has_permission(AUDIT_DOCTYPE, "read", self.audit):
			frappe.throw(_("You can appeal only your own audits."), frappe.PermissionError)

		existing = frappe.db.exists(
			self.doctype,
			{"audit": self.audit, "docstatus": ["<", 2], "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(
				_("Appeal {0} already exists for this audit.").format(
					frappe.get_desk_link(self.doctype, existing)
				)
			)

	def validate_appeal_window(self):
		window = cint(get_settings().appeal_window_days)
		if not window:
			return

		posting_date = frappe.db.get_value(AUDIT_DOCTYPE, self.audit, "posting_date")
		if date_diff(getdate(self.raised_on or nowdate()), getdate(posting_date)) > window:
			frappe.throw(_("An appeal must be raised within {0} days of the audit.").format(window))

	def validate_votes(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id")
		seen = set()
		for row in self.votes:
			if row.panel_member in seen:
				frappe.throw(_("Row {0}: {1} has already voted.").format(row.idx, row.panel_member))
			seen.add(row.panel_member)

			if employee_user and row.panel_member == employee_user:
				frappe.throw(
					_(
						"Row {0}: a panel member does not vote on their own timesheets. Name a substitute instead."
					).format(row.idx)
				)

	def set_decision(self):
		required = cint(get_settings().votes_required) or 2
		accepts = sum(1 for row in self.votes if row.vote == ACCEPT)
		rejects = sum(1 for row in self.votes if row.vote == REJECT)

		self.decision = ""
		if accepts >= required:
			self.decision = "Accepted"
		elif rejects >= required:
			self.decision = "Rejected"
