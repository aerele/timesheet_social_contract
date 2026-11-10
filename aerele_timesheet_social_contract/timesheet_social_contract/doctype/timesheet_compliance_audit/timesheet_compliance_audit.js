// Copyright (c) 2026, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timesheet Compliance Audit", {
	week_start(frm) {
		if (frm.doc.week_start) {
			frm.set_value("week_end", frappe.datetime.add_days(frm.doc.week_start, 6));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && flt(frm.doc.contribution) > 0) {
			frm.add_custom_button(__("Raise Appeal"), () => {
				frappe.new_doc("Timesheet Contribution Appeal", { audit: frm.doc.name });
			});
		}

		if (frm.doc.docstatus === 1 && frm.doc.refund_additional_salary) {
			frm.dashboard.set_headline(
				__("Contribution refunded through {0}.", [frm.doc.refund_additional_salary.bold()])
			);
		}
	},
});
