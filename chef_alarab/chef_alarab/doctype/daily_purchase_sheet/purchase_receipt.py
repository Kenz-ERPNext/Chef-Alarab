# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Purchase Receipt ("goods received") from the Daily Purchase Sheet.

Goods arrive at night: qty is known, the supplier bill (rate) comes in the morning.
So the receipt is made at rate 0 against the "Market Purchase" supplier. Each sheet
Purchase Invoice is then linked to these receipt rows; with Buying Settings
"Set Landed Cost Based on Purchase Invoice Rate" ERPNext moves the invoice rate into
the receipt's valuation and reposts, so Delivery Note cost and Gross Profit get the
real purchase cost.
"""

import frappe
from frappe import _
from frappe.utils import flt

MARKET_SUPPLIER = "Market Purchase"


def make_purchase_receipt(sheet):
	if sheet.docstatus != 1:
		frappe.throw(_("Submit the sheet first."))
	if not sheet.set_warehouse:
		frappe.throw(_("Set the Target Warehouse on the sheet."))
	if not frappe.db.exists("Supplier", MARKET_SUPPLIER):
		frappe.throw(_("Create a Supplier named {0} first.").format(frappe.bold(MARKET_SUPPLIER)))
	frappe.has_permission("Purchase Receipt", "create", throw=True)

	# Only stock items need a receipt; non-stock items go straight to the Purchase Invoice.
	rows = [
		d
		for d in sheet.items
		if flt(d.received_qty) > 0
		and not d.purchase_receipt
		and frappe.get_cached_value("Item", d.item_code, "is_stock_item")
	]
	if not rows:
		frappe.throw(
			_("Nothing to receive. Enter Received Qty for stock items; non-stock items need no Purchase Receipt.")
		)

	pr = frappe.new_doc("Purchase Receipt")
	pr.update(
		{
			"supplier": MARKET_SUPPLIER,
			"company": sheet.company,
			"set_warehouse": sheet.set_warehouse,
			"custom_daily_purchase_sheet": sheet.name,
			"remarks": _("Goods received for delivery date {0} ({1})").format(
				frappe.format(sheet.purchase_date, "Date"), sheet.name
			),
		}
	)
	for row in rows:
		pr.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": row.received_qty,
				"uom": row.uom,
				"conversion_factor": 1,
				"warehouse": sheet.set_warehouse,
				"allow_zero_valuation_rate": 1,
				"custom_dps_item_row": row.name,
			},
		)
	pr.set_missing_values()
	# The buying price list would fill a rate; the real rate comes from the Purchase Invoice.
	for d in pr.items:
		d.price_list_rate = d.rate = d.discount_percentage = d.discount_amount = 0
	pr.taxes_and_charges = None
	pr.set("taxes", [])
	pr.insert()
	pr.submit()
	return pr.name


# ---------- Purchase Receipt doc_events (hooks.py) ----------


def set_item_rows(doc, receipt):
	if not doc.get("custom_daily_purchase_sheet"):
		return
	for d in doc.items:
		if d.get("custom_dps_item_row"):
			frappe.db.set_value(
				"Daily Purchase Sheet Item",
				d.custom_dps_item_row,
				{"purchase_receipt": receipt, "pr_item": d.name if receipt else None},
				update_modified=False,
			)
	sheet = frappe.get_doc("Daily Purchase Sheet", doc.custom_daily_purchase_sheet)
	if sheet.docstatus == 1:
		sheet.set_status(update=True)


def link_item_rows(doc, method=None):
	set_item_rows(doc, doc.name)


def unlink_item_rows(doc, method=None):
	set_item_rows(doc, None)
