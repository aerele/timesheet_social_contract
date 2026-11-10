import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from aerele_timesheet_social_contract.compliance import PANEL_ROLE

CUSTOM_FIELDS = {
	"Timesheet Detail": [
		{
			"fieldname": "sc_submitted_on",
			"fieldtype": "Datetime",
			"label": "Submitted On",
			"insert_after": "description",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"report_hide": 0,
			"description": "When this entry was submitted. Used by the timesheet social contract audit.",
		}
	]
}

SALARY_COMPONENTS = (
	{
		"salary_component": "Social Contract Contribution",
		"salary_component_abbr": "SCC",
		"type": "Deduction",
		"description": "Timesheet social contract contribution, credited to the Team Fund.",
	},
	{
		"salary_component": "Social Contract Refund",
		"salary_component_abbr": "SCR",
		"type": "Earning",
		"is_tax_applicable": 0,
		"description": "Refund of a timesheet social contract contribution.",
	},
)


def before_install():
	# The settings single has Link defaults to these components, and Frappe saves
	# singles (init_singles) before after_install runs, so they must exist first.
	make_salary_components()


def after_install():
	setup()
	from aerele_timesheet_social_contract.patches.backfill_timesheet_submission_times import execute

	execute()


def setup():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	make_role()
	make_salary_components()


def make_role():
	if not frappe.db.exists("Role", PANEL_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": PANEL_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def make_salary_components():
	for component in SALARY_COMPONENTS:
		if frappe.db.exists("Salary Component", component["salary_component"]):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"depends_on_payment_days": 0,
				"remove_if_zero_valued": 1,
				**component,
			}
		)
		doc.insert(ignore_permissions=True, ignore_if_duplicate=True)


def before_uninstall():
	frappe.db.delete("Custom Field", {"dt": "Timesheet Detail", "fieldname": "sc_submitted_on"})
	frappe.clear_cache(doctype="Timesheet Detail")
