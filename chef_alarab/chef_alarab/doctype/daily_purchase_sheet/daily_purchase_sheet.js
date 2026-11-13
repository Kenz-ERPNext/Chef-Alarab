// Copyright (c) 2026, Chef Al Arab and contributors
// For license information, please see license.txt

frappe.ui.form.on("Daily Purchase Sheet", {
	setup(frm) {
		// Only enabled users can be assigned; only active items can be bought.
		frm.set_query("assigned_to", "items", () => ({ filters: { enabled: 1, user_type: "System User" } }));
		frm.set_query("item_code", "items", () => ({ filters: { disabled: 0 } }));
		frm.set_query("sales_order", "sales_orders", () => ({
			filters: { docstatus: 1, company: frm.doc.company },
		}));
		frm.set_query("set_warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},

	purchase_date(frm) {
		load_items(frm);
	},

	company(frm) {
		load_items(frm);
	},

	refresh(frm) {
		// After submit staff only fill in rows; adding or deleting rows is blocked (also on server).
		const locked = frm.doc.docstatus === 1;
		frm.set_df_property("items", "cannot_add_rows", locked);
		frm.set_df_property("items", "cannot_delete_rows", locked);
		frm.set_query("item_code", "supplier_lines", () => ({
			filters: { name: ["in", (frm.doc.items || []).map((d) => d.item_code)] },
		}));
		if (frm.is_new()) return;

		// Buttons by role: Accounts plan and bill, Storekeeper receives, purchase staff only types.
		const accounts = frappe.user.has_role(["Accounts User", "Accounts Manager", "System Manager"]);
		const stock = frappe.user.has_role(["Stock User", "Stock Manager", "System Manager"]);
		const open = frm.doc.docstatus === 1 && frm.doc.status !== "Billed";
		const items = frm.doc.items || [];

		if (accounts && open) {
			frm.add_custom_button(__("Add New Orders"), () => add_new_orders(frm));
		}
		if (stock && frm.doc.docstatus === 1 && items.some((d) => d.is_stock_item && !d.purchase_receipt)) {
			frm.add_custom_button(__("Create Purchase Receipt"), () => create_purchase_receipt(frm)).addClass("btn-primary");
		}
		if (accounts && open) {
			frm.add_custom_button(__("Create Purchase Invoice"), () => create_invoices(frm)).addClass("btn-primary");
		}
	},
});

function load_items(frm) {
	// Draft only: the Delivery Date decides the items (pending qty of that day's Sales Orders).
	if (frm.doc.docstatus !== 0 || !frm.doc.purchase_date || !frm.doc.company) return;
	frm.call({
		doc: frm.doc,
		method: "get_items_from_sales_orders",
		freeze: true,
		freeze_message: __("Collecting Sales Order items..."),
		callback(r) {
			if (r.exc || !r.message) return;
			frm.refresh_fields();
			frm.dirty();
			if (r.message.items) {
				frappe.show_alert({
					message: __("{0} items from {1} Sales Orders", [r.message.items, r.message.sales_orders]),
					indicator: "green",
				});
			} else {
				frappe.show_alert({ message: __("No open Sales Orders for this date."), indicator: "orange" });
			}
		},
	});
}

frappe.ui.form.on("Daily Purchase Sheet Supplier Line", {
	qty: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
});

function create_invoices(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the sheet first."));
		return;
	}
	const lines = frm.doc.supplier_lines || [];
	if (!lines.some((d) => !d.purchase_invoice)) {
		frappe.msgprint({
			title: __("No supplier"),
			message: __("Add the bill in Supplier Lines (Item, Supplier, Qty, Rate), click Update, then try again."),
			indicator: "orange",
		});
		return;
	}
	const with_supplier = new Set(lines.map((d) => d.item_code));
	const missing = (frm.doc.items || []).filter((d) => !with_supplier.has(d.item_code));
	if (missing.length) {
		const names = missing.map((d) => frappe.utils.escape_html(d.item_name || d.item_code)).join(", ");
		frappe.confirm(__("No supplier entered for: {0}. Create invoices for the other items?", [names]), () =>
			make_invoices(frm)
		);
	} else {
		make_invoices(frm);
	}
}

function make_invoices(frm) {
	// Ticked lines only; nothing ticked = all unbilled lines.
	const selected = frm.fields_dict.supplier_lines.grid.get_selected_children().map((d) => d.name);
	frm.call({
		doc: frm.doc,
		method: "create_purchase_invoices",
		args: { line_names: selected.length ? selected : null },
		freeze: true,
		freeze_message: __("Creating Purchase Invoices..."),
		callback(r) {
			if (r.exc || !r.message) return;
			const rows = r.message
				.map(
					(d) =>
						`<li>${frappe.utils.get_form_link("Purchase Invoice", d.name, true)} — ${frappe.utils.escape_html(
							d.supplier
						)} — ${format_currency(d.grand_total)}</li>`
				)
				.join("");
			frappe.msgprint({
				title: __("Draft Purchase Invoices created"),
				message: `<ul>${rows}</ul><p>${__(
					"Open each one, enter the Supplier Invoice No, check tax, then Submit. The sheet updates on submit."
				)}</p>`,
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function set_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.ordered_qty) * flt(row.rate));
}

function add_new_orders(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the sheet first."));
		return;
	}
	frm.call({
		doc: frm.doc,
		method: "add_new_orders",
		freeze: true,
		freeze_message: __("Looking for new Sales Orders..."),
		callback(r) {
			if (r.exc || !r.message) return;
			frm.reload_doc();
			frappe.msgprint({
				title: __("New orders added"),
				message: __(
					"{0} new Sales Orders added. {1} new items. Required Qty updated — assign staff to new rows.",
					[r.message.sales_orders, r.message.new_items]
				),
				indicator: "green",
			});
		},
	});
}

function create_purchase_receipt(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the sheet first."));
		return;
	}
	frappe.confirm(__("Create and submit a Purchase Receipt for the Received Qty?"), () =>
		frm.call({
			doc: frm.doc,
			method: "create_purchase_receipt",
			freeze: true,
			callback(r) {
				if (r.exc || !r.message) return;
				frm.reload_doc();
				frappe.msgprint({
					title: __("Stock received"),
					message: __("Purchase Receipt {0} submitted.", [
						frappe.utils.get_form_link("Purchase Receipt", r.message, true),
					]),
					indicator: "green",
				});
			},
		})
	);
}

