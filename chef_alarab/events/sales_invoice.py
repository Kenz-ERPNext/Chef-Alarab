import json

from frappe.utils import flt


def apply_vat_included_rate(doc, method=None):
	"""Derive the tax-exclusive rate from the VAT-inclusive price entered on each item row."""
	for item in doc.items:
		if not flt(item.custom_vat_included):
			continue

		vat_rate = get_item_vat_rate(doc, item)
		item.rate = flt(flt(item.custom_vat_included) / (1 + vat_rate / 100), item.precision("rate"))


def get_item_vat_rate(doc, item):
	# Same precedence ERPNext uses: item tax template rate overrides the tax row rate
	item_tax_map = json.loads(item.item_tax_rate or "{}")

	vat_rate = 0
	for tax in doc.get("taxes") or []:
		if tax.charge_type != "On Net Total" or tax.included_in_print_rate:
			continue
		vat_rate += flt(item_tax_map.get(tax.account_head, tax.rate))

	return vat_rate
