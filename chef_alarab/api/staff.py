# Copyright (c) 2026, Chef Al Arab and contributors
"""Mobile API for purchase staff (My Purchase Tasks) and the storekeeper (Receive Goods).

Same rule as accounts.py: thin wrappers over the Daily Purchase Sheet, so its validations apply.
The storekeeper's list is blind on purpose: no ordered qty, no rate, no supplier.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from chef_alarab.api.accounts import default_warehouse, find_sheet, sheet_summary
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.daily_purchase_sheet import (
	ACCOUNTS_ROLES,
	STOCK_ROLES,
	require_role,
)
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.purchase_invoice import lines_on_open_invoices

MARKET_SUPPLIER = "Market Purchase"
BUY_ROLES = {"Purchase User", "Purchase Manager", "Accounts User", "Accounts Manager", "System Manager"}


def open_sheet(delivery_date):
	"""The submitted sheet of the date the current user may read, or None."""
	doc = find_sheet(delivery_date)
	if not doc or doc.docstatus != 1:
		return None
	doc.check_permission("read")
	return doc


# ---------- My Purchase Tasks ----------


@frappe.whitelist()
def get_my_tasks(delivery_date: str):
	"""Items assigned to me on the day's sheet, with what I have already bought.

	Accounts / Admin also get the items of other staff (`mine` is false for those), to enter supplier lines for them."""
	require_role(BUY_ROLES, _("see purchase tasks"))
	doc = open_sheet(delivery_date)
	if not doc:
		return None
	me = frappe.session.user
	sees_all = bool(ACCOUNTS_ROLES & set(frappe.get_roles()))
	lines = {}
	for d in doc.supplier_lines:
		lines.setdefault(d.item_code, []).append(
			{
				"supplier": d.supplier,
				"qty": flt(d.qty, 3),
				"rate": flt(d.rate),
				"amount": flt(d.amount),
				"billed": bool(d.purchase_invoice),
			}
		)
	items = [
		{
			"item_code": d.item_code,
			"item_name": d.item_name,
			"uom": d.uom,
			"required_qty": flt(d.required_qty, 3),
			"customer_breakdown": d.customer_breakdown,
			"assigned_to_name": d.assigned_to_name,
			"mine": d.assigned_to == me,
			"lines": lines.get(d.item_code, []),
		}
		for d in doc.items
		if sees_all or d.assigned_to == me
	]
	return {"sheet": doc.name, "status": doc.status, "items": items}


@frappe.whitelist()
def delete_supplier_line(sheet: str, item_code: str, supplier: str):
	"""Remove a mistaken supplier line (a billed line is refused by the sheet)."""
	require_role(BUY_ROLES, _("change supplier lines"))
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	on_invoice = lines_on_open_invoices(doc)
	if any(d.name in on_invoice for d in doc.supplier_lines if d.item_code == item_code and d.supplier == supplier):
		frappe.throw(_("This line is on a Purchase Invoice. Delete that invoice first."))
	doc.set(
		"supplier_lines",
		[d for d in doc.supplier_lines if not (d.item_code == item_code and d.supplier == supplier)],
	)
	doc.save()
	return sheet_summary(doc)


@frappe.whitelist()
def search_suppliers(query: str = "", start: int = 0, page_length: int = 20):
	"""Supplier names matching the text, for the picker."""
	require_role(BUY_ROLES, _("search suppliers"))
	return frappe.get_list(
		"Supplier",
		filters={"disabled": 0, "name": ("!=", MARKET_SUPPLIER)},
		or_filters={"name": ("like", f"%{query}%"), "supplier_name": ("like", f"%{query}%")},
		fields=["name", "supplier_name"],
		order_by="supplier_name",
		limit_start=cint(start),
		limit_page_length=cint(page_length),
	)


# ---------- Receive Goods (blind) ----------


@frappe.whitelist()
def get_receive_items(delivery_date: str):
	"""Item names and units only. The storekeeper weighs what arrived without seeing the order."""
	require_role(STOCK_ROLES, _("receive goods"))
	doc = open_sheet(delivery_date)
	if not doc:
		return None
	return {
		"sheet": doc.name,
		"status": doc.status,
		"items": [
			{
				"item_code": d.item_code,
				"item_name": d.item_name,
				"uom": d.uom,
				"received_qty": flt(d.received_qty, 3),
				"received": bool(d.purchase_receipt) or flt(d.received_qty) > 0,
			}
			for d in doc.items
		],
	}


@frappe.whitelist()
def confirm_received(sheet: str, entries):
	"""Save received qty per item; stock items also get their Purchase Receipt.

	The storekeeper uses the Receive screen; Accounts / Admin enter the same qty on the Order Summary page."""
	require_role(STOCK_ROLES | ACCOUNTS_ROLES, _("receive goods"))
	qty = {e["item_code"]: flt(e["qty"]) for e in frappe.parse_json(entries)}
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	for row in doc.items:
		if row.item_code in qty:
			row.received_qty = qty[row.item_code]
	doc.save()

	receipt = None
	if any(d.is_stock_item and flt(d.received_qty) > 0 and not d.purchase_receipt for d in doc.items):
		if not doc.set_warehouse:
			# Sheets made before the warehouse was filled in automatically: use the site's default.
			if warehouse := default_warehouse(doc.company):
				doc.db_set("set_warehouse", warehouse, update_modified=False)
		receipt = doc.create_purchase_receipt()
	return {"received": len(qty), "receipt": receipt}
