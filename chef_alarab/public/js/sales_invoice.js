frappe.ui.form.on("Sales Invoice Item", {
	custom_vat_included(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.__syncing_vat || !flt(row.custom_vat_included)) return;

		const vat_rate = get_item_vat_rate(frm, row);
		const rate = flt(row.custom_vat_included / (1 + vat_rate / 100), precision("rate", row));
		sync_value(row, "rate", rate);
	},

	rate(frm, cdt, cdn) {
		update_inclusive_rate(frm, locals[cdt][cdn]);
	},

	item_tax_rate(frm, cdt, cdn) {
		update_inclusive_rate(frm, locals[cdt][cdn]);
	},
});

function update_inclusive_rate(frm, row) {
	if (row.__syncing_vat) return;

	const vat_rate = get_item_vat_rate(frm, row);
	const inclusive = flt(row.rate * (1 + vat_rate / 100), precision("custom_vat_included", row));
	sync_value(row, "custom_vat_included", inclusive);
}

// Set one side without letting its change handler recalculate the other side (avoids rounding loops)
function sync_value(row, fieldname, value) {
	if (flt(row[fieldname]) === value) return;

	row.__syncing_vat = true;
	frappe.model.set_value(row.doctype, row.name, fieldname, value).then(() => {
		row.__syncing_vat = false;
	});
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
