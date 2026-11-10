### Aerele Timesheet Social Contract

Runs the Timesheet Social Contract agreed by the Aerele team on 2 November 2026 (effective 1 November 2026) on the Aerele ERP.

Every Sunday it audits the previous Monday to Sunday for each employee, counts the working days whose timesheet was not submitted by the deadline, and adds the week's contribution to the next payroll as an **Additional Salary** under the deduction component **Social Contract Contribution**. The Timesheet Panel handles appeals, and an accepted appeal cancels or refunds the contribution.

### What it adds

| Item | What it does |
| --- | --- |
| **Timesheet Social Contract Settings** | All amounts and rules: base amount, per-day and full-week factors, monthly cap, deadline (grace days, time, time zone, month-end rule), minimum hours per day, salary components, votes required, appeal window, excluded employees. Off until **Enabled** is ticked. |
| **Timesheet Compliance Audit** | One per employee per week. Shows every day (working day, holiday, leave, worked on holiday), its deadline, on-time hours and why it is or isn't compliant. Submitting it creates the Additional Salary. Cancelling it cancels the Additional Salary, or refunds it if a salary slip already deducted it. |
| **Timesheet Contribution Appeal** | Raised by the employee within the appeal window. The panel records votes; a decision needs the configured number of matching votes (default 2 of 3). A panel member can't vote on their own appeal. Submitting an accepted appeal cancels the audit's contribution. |
| **Social Contract Contributions** report | Per employee: weeks audited, working days, non-compliant days, contribution, amount cancelled by the panel, compliance %. The total row is the Team Fund collected for the period. |
| **Submitted On** on Timesheet Detail | Set when a timesheet is submitted. Entries carried over unchanged into an amended timesheet keep their original time; new or changed entries get the amendment's time. |
| **Timesheet Panel** role | Can run and cancel audits, decide appeals, cancel invoiced timesheets. |
| Salary components | **Social Contract Contribution** (Deduction) and **Social Contract Refund** (Earning), created on install if missing. |

### How a day is judged

- **Working day**: a day that is not a holiday (from the employee's Holiday List Assignment) and not approved full-day leave, within joining and relieving dates, on or after the effective date. Any day with a timesheet entry (draft or submitted) is also a working day, including holidays and leave days. Half-day leave is still a working day.
- **Deadline**: the work date plus Grace Days (default 1, so the next calendar day) at Deadline Time (23:59:59) in the Deadline Time Zone (Asia/Kolkata). From the employee's last scheduled working day of the month onwards, the deadline is the same day.
- **Compliant**: submitted entries for that date whose Submitted On is before the deadline add up to more than zero hours (or to the Minimum Hours per Day when that is set). Drafts and cancelled timesheets don't count.
- **Contribution**: non-compliant days x Base Amount x Per-Day Factor. If every working day of the week is non-compliant: Base Amount x Full-Week Factor. Capped per employee per calendar month (by audit date).

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site $SITE install-app aerele_timesheet_social_contract
bench --site $SITE migrate
```

Then, in **Timesheet Social Contract Settings**: set the Company, check the amounts, add excluded employees, assign the **Timesheet Panel** role to the panel, and tick **Enabled**. Make sure the two salary components have accounts set for the company before payroll is run.

### Running the tests

```bash
bench --site $TEST_SITE run-tests --app aerele_timesheet_social_contract
```

### Contributing

This app uses `pre-commit` for code formatting and linting:

```bash
cd apps/aerele_timesheet_social_contract
pre-commit install
```

### License

mit
