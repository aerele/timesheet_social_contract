// Copyright (c) 2026, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timesheet Contribution Appeal", {
	setup(frm) {
		frm.set_query("audit", () => ({
			filters: { docstatus: 1, contribution: [">", 0] },
		}));
	},

	refresh(frm) {
		if (frm.doc.decision) {
			const color = frm.doc.decision === "Accepted" ? "green" : "red";
			frm.dashboard.set_headline_alert(
				`<div class="indicator ${color}">${__("Panel decision: {0}", [__(frm.doc.decision)])}</div>`,
			);
		}
	},
});
