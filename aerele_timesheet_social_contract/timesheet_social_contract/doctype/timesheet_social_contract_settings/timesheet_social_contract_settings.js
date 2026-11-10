// Copyright (c) 2026, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timesheet Social Contract Settings", {
	setup(frm) {
		frm.set_query("deduction_component", () => ({ filters: { type: "Deduction" } }));
		frm.set_query("refund_component", () => ({ filters: { type: "Earning" } }));
	},

	onload(frm) {
		frappe.call({ method: "frappe.core.doctype.user.user.get_timezones" }).then((r) => {
			if (r.message?.timezones) {
				frm.set_df_property("deadline_time_zone", "options", r.message.timezones);
			}
		});
	},

	refresh(frm) {
		if (!frm.doc.enabled) {
			frm.dashboard.set_headline(
				__("The weekly audit is off. Enable it to run every Sunday.")
			);
		}

		frm.add_custom_button(__("Run Audit for a Week"), () => {
			frappe.prompt(
				[
					{
						fieldname: "week_start",
						fieldtype: "Date",
						label: __("Week Start (Monday)"),
						reqd: 1,
						description: __(
							"Leave the latest finished week to audit everyone who has no audit yet."
						),
					},
				],
				(values) => {
					frappe
						.call({
							method: "aerele_timesheet_social_contract.api.run_audit_for_week",
							args: { week_start: values.week_start },
							freeze: true,
						})
						.then((r) => frappe.msgprint(r.message));
				},
				__("Run Audit"),
				__("Run")
			);
		});
	},
});
