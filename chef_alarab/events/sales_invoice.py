import json

from frappe.utils import flt


def sync_inclusive_rate(doc, method=None):
	"""Keep the VAT-inclusive rate in step with the item rate and the current taxes."""
	for item in doc.items:
		vat_rate = get_item_vat_rate(doc, item)
		item.custom_vat_included = flt(
			flt(item.rate) * (1 + vat_rate / 100), item.precision("custom_vat_included")
		)


def get_item_vat_rate(doc, item):
	# Same precedence ERPNext uses: item tax template rate overrides the tax row rate
	item_tax_map = json.loads(item.item_tax_rate or "{}")

	vat_rate = 0
	for tax in doc.get("taxes") or []:
		if tax.charge_type != "On Net Total" or tax.included_in_print_rate:
			continue
		vat_rate += flt(item_tax_map.get(tax.account_head, tax.rate))

	return vat_rate
