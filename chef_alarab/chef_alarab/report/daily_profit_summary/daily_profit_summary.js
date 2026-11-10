// Copyright (c) 2026, Chef Al Arab and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Profit Summary"] = {
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
			fieldname: "include_outside_sale",
			label: __("Include Outside Sale"),
			fieldtype: "Check",
			default: 0,
		},
	],
	onload(report) {
		report.page.add_inner_button(__("Add Outside Sale"), () => edit_outside_sale(report));
		// Click on an Outside Sale cell to add / edit that day's amount.
		report.page.wrapper.on("click", ".os-edit", (e) => {
			const el = $(e.currentTarget);
			edit_outside_sale(report, el.attr("data-date"), el.attr("data-amount"), el.attr("data-note"));
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["profit", "profit_pct"].includes(column.fieldname) && data.profit < 0) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		if (data && column.fieldname === "outside_sale" && !data.is_total) {
			const note = frappe.utils.escape_html(data.note || "");
			value = `<a class="os-edit" title="${__("Edit Outside Sale")}" data-date="${data.date}"
				data-amount="${data.outside_sale || 0}" data-note="${note}">${value} ✏️</a>`;
		}
		if (data && data.is_total) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};

function edit_outside_sale(report, date, amount, note) {
	const d = new frappe.ui.Dialog({
		title: __("Outside Sale"),
		fields: [
			{ fieldname: "sale_date", label: __("Date"), fieldtype: "Date", reqd: 1, default: date || frappe.datetime.get_today(), read_only: !!date },
			{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: flt(amount) },
			{ fieldname: "note", label: __("Note"), fieldtype: "Small Text", default: note || "" },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe.call({
				method: "chef_alarab.chef_alarab.doctype.outside_sale.outside_sale.save_for_day",
				args: { company: report.get_filter_value("company"), ...values },
				freeze: true,
				callback(r) {
					if (r.exc) return;
					d.hide();
					frappe.show_alert({ message: __("Outside Sale saved"), indicator: "green" });
					report.refresh();
				},
			});
		},
	});
	d.show();
}
