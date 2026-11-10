# Copyright (c) 2026, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import flt

from aerele_timesheet_social_contract.compliance import AUDIT_DOCTYPE


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns() -> list[dict]:
	return [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "audits", "label": _("Weeks Audited"), "fieldtype": "Int", "width": 120},
		{"fieldname": "working_days", "label": _("Working Days"), "fieldtype": "Int", "width": 120},
		{
			"fieldname": "non_compliant_days",
			"label": _("Non-Compliant Days"),
			"fieldtype": "Int",
			"width": 150,
		},
		{"fieldname": "contribution", "label": _("Contribution"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "cancelled", "label": _("Cancelled by Panel"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "compliance", "label": _("Compliance %"), "fieldtype": "Percent", "width": 120},
	]


def get_data(filters) -> list[dict]:
	Audit = frappe.qb.DocType(AUDIT_DOCTYPE)
	query = (
		frappe.qb.from_(Audit)
		.select(
			Audit.employee,
			Audit.employee_name,
			Audit.docstatus,
			Count(Audit.name).as_("audits"),
			Sum(Audit.working_days).as_("working_days"),
			Sum(Audit.non_compliant_days).as_("non_compliant_days"),
			Sum(Audit.contribution).as_("contribution"),
		)
		.where(Audit.docstatus.isin([1, 2]))
		.groupby(Audit.employee, Audit.employee_name, Audit.docstatus)
	)
	if filters.from_date:
		query = query.where(Audit.posting_date >= filters.from_date)
	if filters.to_date:
		query = query.where(Audit.posting_date <= filters.to_date)
	if filters.employee:
		query = query.where(Audit.employee == filters.employee)

	rows: dict[str, dict] = {}
	for r in query.run(as_dict=True):
		row = rows.setdefault(
			r.employee,
			frappe._dict(
				employee=r.employee,
				employee_name=r.employee_name,
				audits=0,
				working_days=0,
				non_compliant_days=0,
				contribution=0.0,
				cancelled=0.0,
			),
		)
		if r.docstatus == 1:
			row.audits += r.audits
			row.working_days += r.working_days or 0
			row.non_compliant_days += r.non_compliant_days or 0
			row.contribution += flt(r.contribution)
		else:
			row.cancelled += flt(r.contribution)

	data = sorted(rows.values(), key=lambda r: (-r.contribution, r.employee_name or ""))
	for row in data:
		row.compliance = (
			flt(100 * (row.working_days - row.non_compliant_days) / row.working_days, 1)
			if row.working_days
			else 100
		)
	return data
