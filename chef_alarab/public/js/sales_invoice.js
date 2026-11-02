frappe.ui.form.on("Sales Invoice Item", {
	custom_vat_included(frm, cdt, cdn) {
		apply_vat_included_rate(frm, cdt, cdn);
	},

	item_tax_rate(frm, cdt, cdn) {
		apply_vat_included_rate(frm, cdt, cdn);
	},
});

function apply_vat_included_rate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!flt(row.custom_vat_included)) return;

	const vat_rate = get_item_vat_rate(frm, row);
	const rate = flt(row.custom_vat_included / (1 + vat_rate / 100), precision("rate", row));
	frappe.model.set_value(cdt, cdn, "rate", rate);
}

function get_item_vat_rate(frm, row) {
	// Same precedence ERPNext uses: item tax template rate overrides the tax row rate
	const item_tax_map = JSON.parse(row.item_tax_rate || "{}");

	let vat_rate = 0;
	(frm.doc.taxes || []).forEach((tax) => {
		if (tax.charge_type !== "On Net Total" || tax.included_in_print_rate) return;
		vat_rate += flt(tax.account_head in item_tax_map ? item_tax_map[tax.account_head] : tax.rate);
	});

	return vat_rate;
}
