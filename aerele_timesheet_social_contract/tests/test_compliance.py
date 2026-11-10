"""Rules of the social contract, checked against the examples in the agreement.

These tests build a WeekContext in memory, so they need no employees, holiday lists or
timesheets in the database.
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from aerele_timesheet_social_contract.compliance import (
	WeekContext,
	apply_monthly_cap,
	calculate_contribution,
	get_deadline,
	get_latest_auditable_week_end,
)
from aerele_timesheet_social_contract.timesheet import stamp_rows

WEEK_START = date(2026, 11, 2)  # Monday


def make_settings(**overrides):
	settings = frappe._dict(
		effective_from=date(2026, 11, 1),
		base_amount=5000,
		per_day_factor=0.15,
		full_week_factor=1,
		monthly_cap=20000,
		grace_days=1,
		deadline_time="23:59:59",
		deadline_time_zone="Asia/Kolkata",
		month_end_same_day=1,
		minimum_hours_per_day=0,
	)
	settings.update(overrides)
	return settings


def make_context(
	week_start=WEEK_START, logs=None, holidays=None, leave_days=None, settings=None, employee=None
):
	"""WeekContext with data set directly, Saturday and Sunday as holidays by default."""
	context = WeekContext.__new__(WeekContext)
	context.settings = settings or make_settings()
	context.week_start = week_start
	context.week_end = week_start + timedelta(days=6)
	context.range_start = week_start - timedelta(days=14)
	context.range_end = week_start + timedelta(days=70)
	context.employees = {"EMP-1": frappe._dict(name="EMP-1", company="C", **(employee or {}))}
	context.missing_holiday_list = set()
	if holidays is None:
		holidays = set()
		day = context.range_start
		while day <= context.range_end:
			if day.weekday() >= 5:
				holidays.add(day)
			day += timedelta(days=1)
	context.holidays = {"EMP-1": holidays}
	context.leave_days = {"EMP-1": leave_days or set()}
	context.time_logs = {"EMP-1": logs or []}
	return context


def log(work_date, submitted_on, hours=8, docstatus=1):
	return frappe._dict(
		employee="EMP-1",
		docstatus=docstatus,
		from_time=datetime.combine(work_date, datetime.min.time()).replace(hour=10),
		hours=hours,
		sc_submitted_on=submitted_on,
		timesheet_modified=submitted_on,
	)


def at(day, hour=18):
	return datetime.combine(day, datetime.min.time()).replace(hour=hour)


def weekdays(start=WEEK_START):
	return [start + timedelta(days=i) for i in range(5)]


@patch("aerele_timesheet_social_contract.compliance.get_system_timezone", return_value="Asia/Kolkata")
class TestCompliance(UnitTestCase):
	def evaluate(self, **kwargs):
		return make_context(**kwargs).evaluate("EMP-1")

	def test_everything_on_time(self, _tz):
		result = self.evaluate(logs=[log(d, at(d)) for d in weekdays()])
		self.assertEqual(result["working_days"], 5)
		self.assertEqual(result["non_compliant_days"], 0)
		self.assertEqual(result["calculated_contribution"], 0)

	def test_next_day_is_on_time(self, _tz):
		result = self.evaluate(logs=[log(d, at(d + timedelta(days=1), 23)) for d in weekdays()])
		self.assertEqual(result["non_compliant_days"], 0)

	def test_monday_only(self, _tz):
		# You submit Monday, and nothing for Tuesday to Friday. Four days: INR 3,000.
		monday = WEEK_START
		result = self.evaluate(logs=[log(monday, at(monday))])
		self.assertEqual(result["non_compliant_days"], 4)
		self.assertEqual(result["calculated_contribution"], 3000)

	def test_monday_to_thursday_entered_on_friday(self, _tz):
		# Monday, Tuesday and Wednesday are late; Thursday is on time. Three days: INR 2,250.
		friday = WEEK_START + timedelta(days=4)
		logs = [log(d, at(friday)) for d in weekdays()[:4]] + [log(friday, at(friday))]
		result = self.evaluate(logs=logs)
		self.assertEqual(result["non_compliant_days"], 3)
		self.assertEqual(result["calculated_contribution"], 2250)

	def test_friday_submitted_on_sunday(self, _tz):
		# The deadline was Saturday night. One day: INR 750.
		days = weekdays()
		logs = [log(d, at(d)) for d in days[:4]] + [log(days[4], at(days[4] + timedelta(days=2), 10))]
		result = self.evaluate(logs=logs)
		self.assertEqual(result["non_compliant_days"], 1)
		self.assertEqual(result["calculated_contribution"], 750)

	def test_nothing_submitted(self, _tz):
		# You work Monday to Friday and submit nothing that week. Full week: INR 5,000.
		result = self.evaluate()
		self.assertEqual(result["non_compliant_days"], 5)
		self.assertEqual(result["calculated_contribution"], 5000)

	def test_draft_does_not_count(self, _tz):
		logs = [log(d, at(d)) for d in weekdays()[:4]] + [log(weekdays()[4], None, docstatus=0)]
		result = self.evaluate(logs=logs)
		self.assertEqual(result["non_compliant_days"], 1)
		self.assertIn("draft", result["days"][4]["remarks"].lower())

	def test_leave_is_not_a_working_day(self, _tz):
		days = weekdays()
		result = self.evaluate(logs=[log(d, at(d)) for d in days[1:]], leave_days={days[0]})
		self.assertEqual(result["working_days"], 4)
		self.assertEqual(result["non_compliant_days"], 0)
		self.assertEqual(result["days"][0]["day_type"], "Leave")

	def test_weekend_work_is_a_working_day(self, _tz):
		saturday = WEEK_START + timedelta(days=5)
		logs = [log(d, at(d)) for d in weekdays()] + [log(saturday, at(saturday + timedelta(days=3)))]
		result = self.evaluate(logs=logs)
		self.assertEqual(result["working_days"], 6)
		self.assertEqual(result["days"][5]["day_type"], "Worked on Holiday")
		self.assertEqual(result["non_compliant_days"], 1)

	def test_before_effective_date_and_joining(self, _tz):
		week = date(2026, 10, 26)
		result = self.evaluate(week_start=week, employee={"date_of_joining": None})
		# Only Sunday 1 Nov is on or after the effective date, and it is a holiday.
		self.assertEqual(result["working_days"], 0)

		result = self.evaluate(employee={"date_of_joining": WEEK_START + timedelta(days=3)})
		self.assertEqual(result["working_days"], 2)

	def test_month_end_is_same_day(self, _tz):
		# Monday 30 Nov 2026 is the last working day of November.
		week = date(2026, 11, 30)
		monday = week
		late_by_a_day = self.evaluate(week_start=week, logs=[log(monday, at(monday + timedelta(days=1), 9))])
		self.assertEqual(late_by_a_day["days"][0]["compliant"], 0)

		same_day = self.evaluate(week_start=week, logs=[log(monday, at(monday, 23))])
		self.assertEqual(same_day["days"][0]["compliant"], 1)

		# Tuesday 1 Dec is back to the next-day rule.
		tuesday = week + timedelta(days=1)
		next_day = self.evaluate(week_start=week, logs=[log(tuesday, at(tuesday + timedelta(days=1), 23))])
		self.assertEqual(next_day["days"][1]["compliant"], 1)

	def test_minimum_hours(self, _tz):
		settings = make_settings(minimum_hours_per_day=4)
		result = self.evaluate(logs=[log(d, at(d), hours=2) for d in weekdays()], settings=settings)
		self.assertEqual(result["non_compliant_days"], 5)

	def test_missing_holiday_list_stops_the_audit(self, _tz):
		context = make_context()
		context.missing_holiday_list = {"EMP-1"}
		self.assertRaises(frappe.ValidationError, context.evaluate, "EMP-1")


@patch("aerele_timesheet_social_contract.compliance.get_system_timezone", return_value="Asia/Kolkata")
class TestRules(UnitTestCase):
	def test_contribution_table(self, _tz):
		settings = make_settings()
		self.assertEqual(calculate_contribution(5, 0, settings), 0)
		self.assertEqual(calculate_contribution(5, 1, settings), 750)
		self.assertEqual(calculate_contribution(5, 2, settings), 1500)
		self.assertEqual(calculate_contribution(5, 3, settings), 2250)
		self.assertEqual(calculate_contribution(5, 4, settings), 3000)
		self.assertEqual(calculate_contribution(5, 5, settings), 5000)
		self.assertEqual(calculate_contribution(0, 0, settings), 0)

	def test_contribution_uses_settings(self, _tz):
		settings = make_settings(base_amount=1000, per_day_factor=0.2, full_week_factor=2)
		self.assertEqual(calculate_contribution(5, 2, settings), 400)
		self.assertEqual(calculate_contribution(5, 5, settings), 2000)

	def test_monthly_cap(self, _tz):
		self.assertEqual(apply_monthly_cap(5000, 10000, 20000)[0], 5000)
		amount, note = apply_monthly_cap(5000, 18000, 20000)
		self.assertEqual(amount, 2000)
		self.assertTrue(note)
		self.assertEqual(apply_monthly_cap(5000, 20000, 20000)[0], 0)
		self.assertEqual(apply_monthly_cap(5000, 99999, 0)[0], 5000)

	def test_deadline(self, _tz):
		friday = date(2026, 11, 6)
		self.assertEqual(get_deadline(friday, None, make_settings()), datetime(2026, 11, 7, 23, 59, 59))
		self.assertEqual(get_deadline(friday, friday, make_settings()), datetime(2026, 11, 6, 23, 59, 59))

	def test_deadline_in_other_system_time_zone(self, tz):
		tz.return_value = "UTC"
		self.assertEqual(
			get_deadline(date(2026, 11, 6), None, make_settings()), datetime(2026, 11, 7, 18, 29, 59)
		)

	def test_latest_auditable_week(self, _tz):
		settings = make_settings()
		# Run on Sunday 15 Nov: audits 2 to 8 Nov.
		self.assertEqual(get_latest_auditable_week_end(settings, date(2026, 11, 15)), date(2026, 11, 8))
		# Monday 9 Nov: Sunday 8's deadline (Monday night) has not passed, so 26 Oct to 1 Nov.
		self.assertEqual(get_latest_auditable_week_end(settings, date(2026, 11, 9)), date(2026, 11, 1))
		self.assertEqual(get_latest_auditable_week_end(settings, date(2026, 11, 10)), date(2026, 11, 8))


class TestSubmissionStamps(UnitTestCase):
	def row(self, **kw):
		base = dict(
			from_time="2026-11-02 10:00:00",
			to_time="2026-11-02 12:00:00",
			hours=2,
			activity_type="Development",
			project="P1",
			task="T1",
			is_billable=1,
			description="Work",
		)
		base.update(kw)
		return frappe._dict(base)

	def test_amendment_keeps_original_time_for_unchanged_rows(self):
		original_time = datetime(2026, 11, 2, 19, 0)
		now = datetime(2026, 11, 5, 9, 0)
		original = [
			self.row(sc_submitted_on=original_time),
			self.row(task="T2", sc_submitted_on=original_time),
		]
		amended = [self.row(), self.row(task="T2", description="Changed"), self.row(task="T3")]

		stamp_rows(amended, original, now)

		self.assertEqual(amended[0].sc_submitted_on, original_time)
		self.assertEqual(amended[1].sc_submitted_on, now)
		self.assertEqual(amended[2].sc_submitted_on, now)

	def test_duplicate_rows_inherit_once_each(self):
		t1, t2 = datetime(2026, 11, 2, 19, 0), datetime(2026, 11, 2, 20, 0)
		original = [self.row(sc_submitted_on=t2), self.row(sc_submitted_on=t1)]
		amended = [self.row(), self.row(), self.row()]
		now = datetime(2026, 11, 5)

		stamp_rows(amended, original, now)

		self.assertEqual([r.sc_submitted_on for r in amended], [t1, t2, now])
