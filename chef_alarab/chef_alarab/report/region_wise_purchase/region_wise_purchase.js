// Copyright (c) 2026, Chef Al Arab and contributors
// For license information, please see license.txt

frappe.query_reports["Region Wise Purchase"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "region",
			label: __("Purchase Region"),
			fieldtype: "Link",
			options: "Purchase Region",
		},
	],
	initial_depth: 1,
	onload() {
		add_styles();
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const classes = ["hp"];
		if (data.is_total) classes.push("hp-total");
		else if (data.is_group) classes.push("hp-group", `hp-c${data.color}`);
		else if (column.fieldname === "name") classes.push("hp-vendor", `hp-c${data.color}`);
		if (column.fieldname === "tax") classes.push("hp-vat");
		if (column.fieldname === "total") classes.push("hp-sum");
		return `<span class="${classes.join(" ")}">${value}</span>`;
	},
};

// Region rows get their own colour; the Grand Total is green. Cell backgrounds use :has() on the formatter's span.
function add_styles() {
	if (document.getElementById("region-purchase-style")) return;
	const colors = ["blue", "purple", "orange", "cyan", "pink"];
	const per_color = colors
		.map(
			(c, i) => `
		.dt-cell:has(.hp-group.hp-c${i}) { background: var(--${c}-50); }
		.hp-group.hp-c${i} { color: var(--${c}-700); }
		.hp-vendor.hp-c${i}::before { content: ""; display: inline-block; width: 8px; height: 8px;
			border-radius: 50%; margin-right: 6px; background: var(--${c}-400); }`
		)
		.join("");
	$(`<style id="region-purchase-style">
		${per_color}
		.hp-group { font-weight: 600; }
		.dt-cell:has(.hp-total) { background: var(--green-50); border-top: 2px solid var(--green-400); }
		.hp-total { font-weight: 700; color: var(--green-700); }
		.hp-vat:not(.hp-total) { color: var(--orange-600); }
		.hp-sum { font-weight: 600; }
	</style>`).appendTo("head");
}
