// Copyright (c) 2026, Chef Al Arab and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Profit"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Delivery Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Delivery Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), 7),
			reqd: 1,
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Invoice", "Item", "Customer"].join("\n"),
			default: "Invoice",
		},
		{
			fieldname: "daily_purchase_sheet",
			label: __("Daily Purchase Sheet"),
			fieldtype: "Link",
			options: "Daily Purchase Sheet",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["profit", "profit_pct"].includes(column.fieldname) && data.profit < 0) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		if (data && column.fieldname === "cost_rate" && data.cost_missing) {
			value = `<span title="${__("No supplier rate yet")}" style="color: var(--orange-600)">${value} ⚠</span>`;
		}
		return value;
	},
};
