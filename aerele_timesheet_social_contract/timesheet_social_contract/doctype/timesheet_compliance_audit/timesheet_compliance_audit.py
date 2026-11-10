# Copyright (c) 2026, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, nowdate

from aerele_timesheet_social_contract.compliance import (
	AUDIT_DOCTYPE,
	WeekContext,
	apply_monthly_cap,
	get_contribution_already_charged,
	get_deadline,
	get_excluded_employees,
	get_settings,
)


class TimesheetComplianceAudit(Document):
	# Additional Salary and appeals point back at the audit; cancelling the audit handles them itself.
	ignore_linked_doctypes = ("Additional Salary", "Timesheet Contribution Appeal")

	def validate(self):
		self.validate_week()
		self.validate_duplicate()
		if self.docstatus == 0:
			self.run_audit()

	def before_submit(self):
		# The cap depends on other audits submitted since this one was calculated.
		self.set_contribution()

	def on_submit(self):
		if flt(self.contribution) > 0:
			self.make_contribution_salary()

	def on_cancel(self):
		self.reverse_contribution_salary()

	def validate_week(self):
		week_start = getdate(self.week_start)
		if week_start.weekday() != 0:
			frappe.throw(_("Week Start must be a Monday."))

		self.week_end = week_start + timedelta(days=6)
		settings = get_settings()

		if getdate(self.week_end) < getdate(settings.effective_from):
			frappe.throw(_("This week ends before the social contract's effective date."))

		last_deadline = get_deadline(getdate(self.week_end), None, settings)
		if now_datetime() <= last_deadline:
			frappe.throw(
				_(
					"This week can be audited only after {0}, when its last submission deadline has passed."
				).format(frappe.format_value(last_deadline, {"fieldtype": "Datetime"}))
			)

		if self.employee in get_excluded_employees(settings):
			frappe.throw(_("Employee {0} is excluded from the social contract.").format(self.employee))

	def validate_duplicate(self):
		existing = frappe.db.exists(
			AUDIT_DOCTYPE,
			{
				"employee": self.employee,
				"week_start": self.week_start,
				"docstatus": ["<", 2],
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_("Audit {0} already exists for this employee and week.").format(
					frappe.get_desk_link(AUDIT_DOCTYPE, existing)
				),
				frappe.DuplicateEntryError,
			)

	def run_audit(self, context: WeekContext | None = None):
		context = context or self.flags.week_context
		if not context:
			employee = frappe.db.get_value(
				"Employee",
				self.employee,
				["name", "company", "date_of_joining", "relieving_date"],
				as_dict=True,
			)
			context = WeekContext(get_settings(), self.week_start, [employee])

		result = context.evaluate(self.employee)
		self.working_days = result["working_days"]
		self.compliant_days = result["compliant_days"]
		self.non_compliant_days = result["non_compliant_days"]
		self.calculated_contribution = result["calculated_contribution"]

		self.set("days", [])
		for day in result["days"]:
			self.append("days", day)

		self.set_contribution()

	def set_contribution(self):
		settings = get_settings()
		already = get_contribution_already_charged(self.employee, self.posting_date, exclude=self.name)
		self.contribution, self.cap_note = apply_monthly_cap(
			flt(self.calculated_contribution), already, flt(settings.monthly_cap)
		)

	def get_payroll_date(self):
		payroll_date = getdate(self.posting_date)
		relieving_date = frappe.db.get_value("Employee", self.employee, "relieving_date")
		if relieving_date and payroll_date > getdate(relieving_date):
			payroll_date = getdate(relieving_date)
		return payroll_date

	def make_contribution_salary(self):
		settings = get_settings()
		additional_salary = make_additional_salary(
			self,
			component=settings.deduction_component,
			amount=self.contribution,
			payroll_date=self.get_payroll_date(),
			submit=settings.submit_additional_salary,
		)
		self.db_set("additional_salary", additional_salary.name)

	def reverse_contribution_salary(self):
		if not self.additional_salary:
			return

		additional_salary = frappe.get_doc("Additional Salary", self.additional_salary)
		if additional_salary.docstatus == 0:
			additional_salary.flags.ignore_permissions = True
			additional_salary.delete()
			self.db_set("additional_salary", None)
			return

		if additional_salary.docstatus == 2:
			return

		if is_paid_in_salary_slip(additional_salary.name):
			# Already deducted: refund it in the next payroll.
			settings = get_settings()
			refund = make_additional_salary(
				self,
				component=settings.refund_component,
				amount=additional_salary.amount,
				payroll_date=max(getdate(nowdate()), getdate(additional_salary.payroll_date)),
				submit=settings.submit_additional_salary,
			)
			self.db_set("refund_additional_salary", refund.name)
		else:
			additional_salary.flags.ignore_permissions = True
			additional_salary.flags.ignore_links = True
			additional_salary.cancel()


def is_paid_in_salary_slip(additional_salary: str) -> bool:
	return bool(
		frappe.db.exists(
			"Salary Detail",
			{"additional_salary": additional_salary, "parenttype": "Salary Slip", "docstatus": 1},
		)
	)


def get_employee_currency(employee: str, company: str) -> str:
	return frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1},
		"currency",
		order_by="from_date desc",
	) or frappe.get_cached_value("Company", company, "default_currency")


def make_additional_salary(audit, component: str, amount: float, payroll_date, submit: bool = True):
	"""Additional Salary for an audit. Only users who can submit or cancel the audit reach this,
	so the Additional Salary itself is created without the user's payroll permissions."""
	doc = frappe.new_doc("Additional Salary")
	doc.update(
		{
			"employee": audit.employee,
			"company": audit.company,
			"salary_component": component,
			"amount": flt(amount, 2),
			"payroll_date": payroll_date,
			"currency": get_employee_currency(audit.employee, audit.company),
			"overwrite_salary_structure_amount": 0,
			"ref_doctype": AUDIT_DOCTYPE,
			"ref_docname": audit.name,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	if submit:
		doc.submit()
	return doc
