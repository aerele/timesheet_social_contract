app_name = "aerele_timesheet_social_contract"
app_title = "Aerele Timesheet Social Contract"
app_publisher = "Aerele Technologies Private Limited"
app_description = (
	"Timesheet compliance social contract: weekly audit, contributions as Additional Salary, panel appeals"
)
app_email = "hello@aerele.in"
app_license = "mit"

required_apps = ["erpnext", "hrms"]

# Installation
# ------------

after_install = "aerele_timesheet_social_contract.setup.install.after_install"
before_uninstall = "aerele_timesheet_social_contract.setup.install.before_uninstall"

# Permissions
# -----------

permission_query_conditions = {
	"Timesheet Compliance Audit": "aerele_timesheet_social_contract.permissions.audit_query_conditions",
	"Timesheet Contribution Appeal": "aerele_timesheet_social_contract.permissions.appeal_query_conditions",
}

has_permission = {
	"Timesheet Compliance Audit": "aerele_timesheet_social_contract.permissions.has_permission",
	"Timesheet Contribution Appeal": "aerele_timesheet_social_contract.permissions.has_permission",
}

# Document Events
# ---------------

doc_events = {
	"Timesheet": {
		"before_submit": "aerele_timesheet_social_contract.timesheet.before_submit",
		"before_cancel": "aerele_timesheet_social_contract.timesheet.before_cancel",
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		# Every Sunday at 00:30 (system time zone): audit the previous Monday to Sunday.
		"30 0 * * 0": ["aerele_timesheet_social_contract.audit.run_weekly_audit"],
	}
}
