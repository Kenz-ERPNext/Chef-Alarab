// Copyright (c) 2026, Chef Al Arab and contributors
// For license information, please see license.txt

frappe.query_reports["Product Profit"] = {
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
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "item_code", label: __("Product"), fieldtype: "Link", options: "Item" },
		{ fieldname: "sales_invoice", label: __("Sales Invoice"), fieldtype: "Link", options: "Sales Invoice" },
	],
	initial_depth: 0,
	onload() {
		add_styles();
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const classes = ["pp", `pp-${data.row_type}`];
		if (["profit", "profit_pct"].includes(column.fieldname) && data.profit < 0) classes.push("pp-loss");
		const n = column.fieldname.match(/^purchase_profit_(\d)$/);
		if (n) classes.push(data[`purchase_loss_${n[1]}`] ? "pp-loss" : "pp-gain");
		// Never bought: no purchase rate, so the cost is 0 and the profit is too high.
		if (column.fieldname === "last_rates" && data.cost_missing) classes.push("pp-left");
		return `<span class="${classes.join(" ")}">${value}</span>`;
	},
};

// Product rows blue; profit green, a loss red.
function add_styles() {
	if (document.getElementById("product-profit-style")) return;
	$(`<style id="product-profit-style">
		.dt-cell:has(.pp-product) { background: var(--blue-50); }
		.pp-product { font-weight: 600; color: var(--blue-700); }
		.pp-gain { color: var(--green-700); font-weight: 600; }
		.pp-loss { color: var(--red-600) !important; }
		.pp-left { color: var(--orange-600); font-weight: 600; }
	</style>`).appendTo("head");
}
