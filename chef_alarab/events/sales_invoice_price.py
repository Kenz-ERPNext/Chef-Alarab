"""Sales Invoice takes today's selling price (Item Price), not the SO / DN rate."""

import frappe
from frappe import _
from frappe.utils import flt


def apply_current_price(doc, method=None):
	"""New invoice from a DN / SO: a rate typed on the invoice wins; a 0 rate is filled from Item Price."""
	if doc.is_return or not doc.selling_price_list:
		return
	for item in doc.items:
		if not (item.delivery_note or item.sales_order) or flt(item.rate):
			continue
		price = get_selling_price(item.item_code, doc.selling_price_list, item.uom, doc.posting_date)
		if price is not None:
			item.price_list_rate = price
			item.discount_percentage = 0
			item.discount_amount = 0
			item.rate = price


def block_zero_rate(doc, method=None):
	missing = [f"#{d.idx} {d.item_code}" for d in doc.items if not flt(d.rate) and not doc.is_return]
	if missing:
		frappe.throw(
			_("Rate is 0 for {0}. Add an Item Price in {1}.").format(", ".join(missing), doc.selling_price_list),
			title=_("Missing selling price"),
		)


def get_selling_price(item_code, price_list, uom, date):
	# Latest valid price for the UOM; falls back to a price without UOM.
	prices = frappe.get_all(
		"Item Price",
		filters={"item_code": item_code, "price_list": price_list, "selling": 1},
		or_filters=[["valid_from", "is", "not set"], ["valid_from", "<=", date]],
		fields=["price_list_rate", "uom", "valid_upto"],
		order_by="valid_from desc, modified desc",
	)
	for match_uom in (uom, None):
		for p in prices:
			if (p.uom or None) == match_uom and (not p.valid_upto or str(p.valid_upto) >= str(date)):
				return flt(p.price_list_rate)
	return None


ZERO_BILLING_WARNING = "System will not check over billing since amount for Item"


def hide_zero_billing_warning(doc, method=None):
	"""Our SO / DN can have rate 0 (price is set on the invoice), so ERPNext's warning is noise."""
	texts = (ZERO_BILLING_WARNING, _(ZERO_BILLING_WARNING + " {0} in {1} is zero").split("{0}")[0].strip())
	log = getattr(frappe.local, "message_log", None) or []
	frappe.local.message_log = [
		m for m in log if not any(t in str(m.get("message") if isinstance(m, dict) else m) for t in texts)
	]
