// Copyright (c) 2026, Aerele Technologies Private Limited and contributors
// For license information, please see license.txt

frappe.listview_settings["Timesheet Compliance Audit"] = {
	add_fields: ["non_compliant_days", "contribution", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 2) {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		}
		if (!doc.non_compliant_days) {
			return [__("Compliant"), "green", "non_compliant_days,=,0"];
		}
		return [__("Non-Compliant"), "orange", "non_compliant_days,>,0"];
	},
};
