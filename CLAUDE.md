# CLAUDE.md: aerele_timesheet_social_contract

Based on the Aerele Frappe CLAUDE.md template: https://aerele.in/frappe-claude-md/

## Stack

- Frappe 16.54, ERPNext 16.52.1, HRMS 16.52 (as on insider.frappe.cloud). Use only APIs that exist in these versions.
- Python 3.14, Node 24.
- App: `aerele_timesheet_social_contract`, module `Timesheet Social Contract`.
- Bench: `~/Documents/frappe/16-bench` (local develop bench; activate `../16_env`).
- Sites: dev `v16-dev`, test `v16-test`, production `insider.frappe.cloud`.

## Commands

Always pass `--site`.

```bash
bench --site v16-dev migrate
bench build --app aerele_timesheet_social_contract
bench --site v16-test run-tests --app aerele_timesheet_social_contract
pre-commit run --all-files
```

- Run tests only on the test site.
- Never run reinstall, drop-site, restore, `--force`, or anything against insider.frappe.cloud. Ask first.
- Start `bench start` only in the background, and only if it is not already running.

## How to work

- Read the existing code first and follow its patterns. The rules live in `compliance.py`; doctypes call into it.
- Plan and confirm any change that touches more than about three files.
- The business rules come from the signed "Timesheet Social Contract" document. If a rule is unclear, ask; do not invent one. Amounts and factors belong in Timesheet Social Contract Settings, not in code.
- Reproduce bugs before fixing them, fix root causes, keep diffs small.
- Done means migrate, tests and pre-commit all pass.

## Framework rules

- Never edit core apps. Extend through hooks, custom fields (`setup/install.py`), property setters and patches.
- Schema or data changes go in idempotent patches listed in `patches.txt`. Patches don't run on a fresh install, so `after_install` must do the same setup.
- Bump `modified` when hand-editing doctype JSON.

## Security

- Parameterised SQL / query builder only.
- Whitelisted methods: permission check (`frappe.only_for` or `has_permission`), type hints, explicit HTTP method.
- `ignore_permissions` only where the caller has already been authorised (e.g. Additional Salary created when a panel member submits an audit). Say why in a comment.
- Employees see only their own audits and appeals (`permissions.py`). Keep that true for any new doctype or report.

## Transactions

- No manual `commit` / `rollback` in requests. The weekly audit uses a savepoint per employee so one failure doesn't stop the batch.
- Validate in `validate`; side effects (Additional Salary) in `on_submit` / `on_cancel`.
- Don't put `frappe.throw` inside a broad try/except.

## ERPNext / HRMS

- Payroll changes only through Additional Salary. Never edit salary slips directly.
- Never hardcode the company, components or accounts. They come from settings.
- Use Frappe's `flt`, `getdate`, `add_days` and HRMS holiday list helpers.

## Performance

- The audit for all employees loads timesheets, leave and holidays in bulk (`WeekContext`). No queries per employee per day.
- Timesheet hooks run on every submit: keep them light.

## Code quality and tests

- No dead code, no `print`, no bare `except`, translatable strings with `_()`.
- Rule changes need tests in `tests/test_compliance.py`, using the agreement's worked examples where they apply.
- A changed test assertion needs a written reason.

## Git

- Branches `feat/...` or `fix/...`, conventional commits.
- Never commit `site_config.json`, keys or `.env`.
