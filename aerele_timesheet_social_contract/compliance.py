"""Timesheet compliance engine.

Works out, for one week (Monday to Sunday), which days were working days for an
employee, the submission deadline of each day and whether the day's timesheet
was submitted on time. All data for a week is loaded in a few bulk queries by
`WeekContext`, so auditing every employee does not run queries per employee.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, get_system_timezone, get_time, getdate, nowdate

SETTINGS_DOCTYPE = "Timesheet Social Contract Settings"
AUDIT_DOCTYPE = "Timesheet Compliance Audit"
PANEL_ROLE = "Timesheet Panel"

# How far back from a month end we look to find the last working day of the month.
MONTH_END_LOOKBACK_DAYS = 14

DAY_WORKING = "Working Day"
DAY_WORKED_ON_HOLIDAY = "Worked on Holiday"
DAY_HOLIDAY = "Holiday"
DAY_LEAVE = "Leave"
DAY_NOT_EMPLOYED = "Not Employed"
DAY_BEFORE_EFFECTIVE = "Before Effective Date"


def get_settings():
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def get_week_bounds(any_date) -> tuple[date, date]:
	"""Monday and Sunday of the week containing `any_date`."""
	d = getdate(any_date)
	start = d - timedelta(days=d.weekday())
	return start, start + timedelta(days=6)


def get_latest_auditable_week_end(settings, today=None) -> date:
	"""Latest Sunday whose last deadline (Sunday + grace days) is fully in the past."""
	reference = getdate(today or nowdate()) - timedelta(days=cint(settings.grace_days) + 1)
	return reference - timedelta(days=(reference.weekday() + 1) % 7)


def get_excluded_employees(settings) -> set[str]:
	return {row.employee for row in settings.excluded_employees}


def calculate_contribution(working_days: int, non_compliant_days: int, settings) -> float:
	"""Contribution for one week before the monthly cap.

	Each non-compliant working day = base x per-day factor. When none of the week's
	working days are compliant, the week is charged base x full-week factor instead.
	"""
	if not working_days or not non_compliant_days:
		return 0.0

	base = flt(settings.base_amount)
	if non_compliant_days >= working_days:
		return flt(base * flt(settings.full_week_factor), 2)

	return flt(non_compliant_days * base * flt(settings.per_day_factor), 2)


def get_contribution_already_charged(employee: str, posting_date, exclude: str | None = None) -> float:
	"""Total contribution of submitted audits for the employee in the calendar month of `posting_date`."""
	posting_date = getdate(posting_date)
	month_start = posting_date.replace(day=1)
	month_end = get_last_day(posting_date)

	Audit = frappe.qb.DocType(AUDIT_DOCTYPE)
	query = (
		frappe.qb.from_(Audit)
		.select(frappe.query_builder.functions.Sum(Audit.contribution))
		.where(
			(Audit.employee == employee)
			& (Audit.docstatus == 1)
			& (Audit.posting_date >= month_start)
			& (Audit.posting_date <= month_end)
		)
	)
	if exclude:
		query = query.where(Audit.name != exclude)

	result = query.run()
	return flt(result[0][0]) if result else 0.0


def apply_monthly_cap(amount: float, already_charged: float, monthly_cap: float) -> tuple[float, str | None]:
	"""Returns the amount after the cap and a note when the cap reduced it."""
	if not flt(monthly_cap) or not flt(amount):
		return flt(amount, 2), None

	allowed = max(0.0, flt(monthly_cap) - flt(already_charged))
	if flt(amount) <= allowed:
		return flt(amount, 2), None

	note = _("Reduced from {0} to {1}: monthly cap of {2}, {3} already charged this month.").format(
		frappe.format_value(amount, {"fieldtype": "Currency"}),
		frappe.format_value(allowed, {"fieldtype": "Currency"}),
		frappe.format_value(monthly_cap, {"fieldtype": "Currency"}),
		frappe.format_value(already_charged, {"fieldtype": "Currency"}),
	)
	return flt(allowed, 2), note


def get_deadline(work_date: date, month_last_working_day: date | None, settings) -> datetime:
	"""Submission deadline for `work_date`, as a naive datetime in the system time zone."""
	deadline_date = work_date
	same_day = (
		cint(settings.month_end_same_day)
		and month_last_working_day is not None
		and work_date >= month_last_working_day
	)
	if not same_day:
		deadline_date = work_date + timedelta(days=cint(settings.grace_days))

	local = datetime.combine(deadline_date, get_time(settings.deadline_time or "23:59:59"))
	local = local.replace(tzinfo=ZoneInfo(settings.deadline_time_zone or "Asia/Kolkata"))
	return local.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


class WeekContext:
	"""Loads everything needed to audit a set of employees for one week."""

	def __init__(self, settings, week_start, employees: list[dict]):
		self.settings = settings
		self.week_start = getdate(week_start)
		self.week_end = self.week_start + timedelta(days=6)
		self.employees = {e["name"]: frappe._dict(e) for e in employees}

		# Holidays and leave are loaded from before the week up to the end of the last month the
		# week touches, so the last working day of that month can be found.
		self.range_start = self.week_start - timedelta(days=MONTH_END_LOOKBACK_DAYS)
		self.range_end = get_last_day(self.week_end)

		names = list(self.employees)
		self.holidays = self._load_holidays(names)
		self.leave_days = self._load_leave_days(names)
		self.time_logs = self._load_time_logs(names)

	def _load_holidays(self, names: list[str]) -> dict[str, set[date]]:
		self.missing_holiday_list = set()
		if not names:
			return {}

		from hrms.utils.holiday_list import (
			get_holiday_list_ranges_for_employees,
			get_holidays_in_ranges_map,
		)

		ranges = get_holiday_list_ranges_for_employees(
			{name: emp.company for name, emp in self.employees.items()},
			self.range_start,
			self.range_end,
			raise_exception=False,
		)
		self.missing_holiday_list = set(names) - set(ranges)
		holidays = get_holidays_in_ranges_map(ranges)
		return {name: {getdate(h.holiday_date) for h in rows} for name, rows in holidays.items()}

	def _load_leave_days(self, names: list[str]) -> dict[str, set[date]]:
		"""Full days of approved leave. Half days still count as working days."""
		if not names:
			return {}

		leaves = frappe.get_all(
			"Leave Application",
			filters={
				"employee": ["in", names],
				"status": "Approved",
				"docstatus": 1,
				"from_date": ["<=", self.range_end],
				"to_date": [">=", self.range_start],
			},
			fields=["employee", "from_date", "to_date", "half_day", "half_day_date"],
		)

		result: dict[str, set[date]] = {}
		for leave in leaves:
			start = max(getdate(leave.from_date), self.range_start)
			end = min(getdate(leave.to_date), self.range_end)
			half_day_date = None
			if cint(leave.half_day):
				half_day_date = getdate(leave.half_day_date or leave.from_date)

			day = start
			while day <= end:
				if day != half_day_date:
					result.setdefault(leave.employee, set()).add(day)
				day += timedelta(days=1)
		return result

	def _load_time_logs(self, names: list[str]) -> dict[str, list[dict]]:
		"""Rows of draft and submitted timesheets whose work date falls in the week."""
		if not names:
			return {}

		Timesheet = frappe.qb.DocType("Timesheet")
		Detail = frappe.qb.DocType("Timesheet Detail")
		rows = (
			frappe.qb.from_(Detail)
			.join(Timesheet)
			.on(Detail.parent == Timesheet.name)
			.select(
				Timesheet.employee,
				Timesheet.name.as_("timesheet"),
				Timesheet.docstatus,
				Timesheet.modified.as_("timesheet_modified"),
				Detail.from_time,
				Detail.hours,
				Detail.sc_submitted_on,
			)
			.where(
				(Detail.parenttype == "Timesheet")
				& (Timesheet.employee.isin(names))
				& (Timesheet.docstatus.isin([0, 1]))
				& (Detail.from_time >= datetime.combine(self.week_start, datetime.min.time()))
				& (
					Detail.from_time
					< datetime.combine(self.week_end + timedelta(days=1), datetime.min.time())
				)
			)
		).run(as_dict=True)

		result: dict[str, list[dict]] = {}
		for row in rows:
			result.setdefault(row.employee, []).append(row)
		return result

	def _is_employed(self, employee, day: date) -> bool:
		if employee.date_of_joining and day < getdate(employee.date_of_joining):
			return False
		if employee.relieving_date and day > getdate(employee.relieving_date):
			return False
		return True

	def _is_scheduled_working_day(self, employee, day: date) -> bool:
		return (
			self._is_employed(employee, day)
			and day not in self.holidays.get(employee.name, set())
			and day not in self.leave_days.get(employee.name, set())
		)

	def _month_last_working_day(self, employee, day: date) -> date | None:
		month_end = get_last_day(day)
		candidate = month_end
		while candidate >= max(month_end - timedelta(days=MONTH_END_LOOKBACK_DAYS), self.range_start):
			if self._is_scheduled_working_day(employee, candidate):
				return candidate
			candidate -= timedelta(days=1)
		return None

	def evaluate(self, employee_name: str) -> dict:
		"""Day-by-day result for one employee."""
		employee = self.employees[employee_name]
		if employee_name in self.missing_holiday_list:
			# Without a holiday list every day would count as a working day.
			frappe.throw(
				_("No Holiday List is assigned to Employee {0} for {1} to {2}.").format(
					frappe.bold(employee_name), self.week_start, self.week_end
				)
			)

		effective_from = getdate(self.settings.effective_from)
		min_hours = flt(self.settings.minimum_hours_per_day)

		logs_by_day: dict[date, list[dict]] = {}
		for row in self.time_logs.get(employee_name, []):
			logs_by_day.setdefault(getdate(row.from_time), []).append(row)

		days = []
		for offset in range(7):
			day = self.week_start + timedelta(days=offset)
			logs = logs_by_day.get(day, [])
			days.append(self._evaluate_day(employee, day, logs, effective_from, min_hours))

		working = [d for d in days if d["is_working_day"]]
		non_compliant = [d for d in working if not d["compliant"]]
		return {
			"days": days,
			"working_days": len(working),
			"compliant_days": len(working) - len(non_compliant),
			"non_compliant_days": len(non_compliant),
			"calculated_contribution": calculate_contribution(
				len(working), len(non_compliant), self.settings
			),
		}

	def _evaluate_day(self, employee, day: date, logs: list[dict], effective_from: date, min_hours: float):
		row = {
			"date": day,
			"weekday": day.strftime("%A"),
			"is_working_day": 0,
			"compliant": 0,
			"submitted_hours": 0,
			"on_time_hours": 0,
			"deadline": None,
			"first_submission": None,
			"remarks": "",
		}

		if day < effective_from:
			row["day_type"] = DAY_BEFORE_EFFECTIVE
			return row
		if not self._is_employed(employee, day):
			row["day_type"] = DAY_NOT_EMPLOYED
			return row

		worked = bool(logs)
		remarks = []
		if day in self.holidays.get(employee.name, set()):
			row["day_type"] = DAY_WORKED_ON_HOLIDAY if worked else DAY_HOLIDAY
		elif day in self.leave_days.get(employee.name, set()):
			row["day_type"] = DAY_WORKING if worked else DAY_LEAVE
			if worked:
				remarks.append(_("Timesheet entered on a day of approved leave."))
		else:
			row["day_type"] = DAY_WORKING

		if row["day_type"] not in (DAY_WORKING, DAY_WORKED_ON_HOLIDAY):
			return row

		row["is_working_day"] = 1
		deadline = get_deadline(day, self._month_last_working_day(employee, day), self.settings)
		row["deadline"] = deadline

		submitted = [log for log in logs if cint(log.docstatus) == 1]
		inferred = False
		submission_times = []
		on_time_hours = 0.0
		for log in submitted:
			submitted_on = log.sc_submitted_on
			if not submitted_on:
				# Submitted before this app recorded submission times.
				submitted_on = log.timesheet_modified
				inferred = True
			submitted_on = frappe.utils.get_datetime(submitted_on)
			submission_times.append(submitted_on)
			if submitted_on <= deadline:
				on_time_hours += flt(log.hours)

		row["submitted_hours"] = flt(sum(flt(log.hours) for log in submitted), 2)
		row["on_time_hours"] = flt(on_time_hours, 2)
		row["first_submission"] = min(submission_times) if submission_times else None

		if not submitted:
			remarks.append(_("Only a draft timesheet.") if logs else _("No submitted timesheet."))
		elif not on_time_hours:
			remarks.append(_("Submitted after the deadline."))
		elif min_hours and on_time_hours < min_hours:
			remarks.append(_("On-time hours below the minimum of {0}.").format(min_hours))
		else:
			row["compliant"] = 1

		if inferred:
			remarks.append(_("Submission time taken from the timesheet's last modified time."))

		row["remarks"] = " ".join(remarks)
		return row


def get_employees_for_week(
	company: str, week_start, week_end, excluded: set[str], only: list[str] | None = None
):
	"""Employees of the company who were employed for at least one day of the week."""
	Employee = frappe.qb.DocType("Employee")
	query = (
		frappe.qb.from_(Employee)
		.select(Employee.name, Employee.company, Employee.date_of_joining, Employee.relieving_date)
		.where(
			(Employee.company == company)
			& (Employee.date_of_joining.isnull() | (Employee.date_of_joining <= week_end))
			& (Employee.relieving_date.isnull() | (Employee.relieving_date >= week_start))
			& (
				(Employee.status == "Active")
				| ((Employee.status == "Left") & Employee.relieving_date.notnull())
			)
		)
	)
	if only:
		query = query.where(Employee.name.isin(only))

	return [e for e in query.run(as_dict=True) if e.name not in excluded]
