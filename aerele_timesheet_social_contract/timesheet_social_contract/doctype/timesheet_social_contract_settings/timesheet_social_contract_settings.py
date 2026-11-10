# Copyright (c) 2026, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class TimesheetSocialContractSettings(Document):
	def validate(self):
		self.validate_time_zone()
		self.validate_components()
		self.validate_numbers()
		self.validate_exclusions()

	def validate_time_zone(self):
		try:
			ZoneInfo(self.deadline_time_zone)
		except ZoneInfoNotFoundError, ValueError:
			frappe.throw(_("{0} is not a valid time zone.").format(self.deadline_time_zone))

	def validate_components(self):
		expected = {self.deduction_component: "Deduction", self.refund_component: "Earning"}
		for component, component_type in expected.items():
			if component and frappe.db.get_value("Salary Component", component, "type") != component_type:
				frappe.throw(
					_("Salary Component {0} must be of type {1}.").format(component, _(component_type))
				)

	def validate_numbers(self):
		if cint(self.votes_required) < 1:
			frappe.throw(_("Votes Required must be at least 1."))
		if flt(self.per_day_factor) > flt(self.full_week_factor):
			frappe.msgprint(
				_("The per-day factor is higher than the full-week factor. Please check this is intended."),
				indicator="orange",
				alert=True,
			)

	def validate_exclusions(self):
		seen = set()
		for row in self.excluded_employees:
			if row.employee in seen:
				frappe.throw(_("Row {0}: Employee {1} is listed twice.").format(row.idx, row.employee))
			seen.add(row.employee)
