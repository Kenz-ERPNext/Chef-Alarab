// Copyright (c) 2026, Chef Al Arab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Outside Sale", {
	refresh(frm) {
		frm.set_intro(__("Not posted to accounts. Shown only in the Daily Profit Summary report."), "blue");
	},
});
