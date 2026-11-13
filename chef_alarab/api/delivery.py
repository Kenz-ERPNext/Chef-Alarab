# Copyright (c) 2026, Chef Al Arab and contributors
"""Mobile API for deliveries: the day's orders to deliver, weighing, and the Delivery Note."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from chef_alarab.api.accounts import apply_default_sales_taxes, pdf_to_png
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.daily_purchase_sheet import (
	ACCOUNTS_ROLES,
	STOCK_ROLES,
	require_role,
)

DELIVERY_ROLES = ACCOUNTS_ROLES | STOCK_ROLES


@frappe.whitelist()
def get_deliveries(delivery_date: str):
	"""Submitted Sales Orders of the day with their delivery state (to weigh / delivered)."""
	require_role(DELIVERY_ROLES, _("see deliveries"))
	rows = frappe.db.sql(
		"""
		SELECT so.name, so.customer_name, so.per_delivered,
			COUNT(soi.name) AS items, SUM(soi.qty * soi.conversion_factor) AS qty
		FROM `tabSales Order` so
		JOIN `tabSales Order Item` soi ON soi.parent = so.name
		WHERE so.docstatus = 1 AND so.status NOT IN ('Closed', 'Cancelled') AND soi.delivery_date = %s
		GROUP BY so.name
		ORDER BY so.customer_name
		""",
		getdate(delivery_date),
		as_dict=True,
	)
	for r in rows:
		r["state"] = (
			"delivered" if flt(r.per_delivered) >= 100 else "partial" if flt(r.per_delivered) > 0 else "to_weigh"
		)
		notes = frappe.get_all(
			"Delivery Note Item",
			filters={"against_sales_order": r.name, "docstatus": 1},
			pluck="parent",
			order_by="creation",
		)
		notes = list(dict.fromkeys(notes))
		invoices = {n: invoice_of(n) for n in notes}
		r["delivery_note"] = notes[-1] if notes else None
		# The first Delivery Note that still has no Sales Invoice (the app offers "Create Sales Invoice" for it).
		r["to_invoice"] = next((n for n in notes if not invoices[n]), None)
		r["invoice"] = next((i for i in reversed(list(invoices.values())) if i), None)
	return rows


def invoice_of(delivery_note):
	"""Name of the (draft or submitted) Sales Invoice made from this Delivery Note, if any."""
	return frappe.db.get_value("Sales Invoice Item", {"delivery_note": delivery_note, "docstatus": ("<", 2)}, "parent")


@frappe.whitelist()
def get_delivery(sales_order: str):
	"""Items still to deliver on one order, to be weighed."""
	require_role(DELIVERY_ROLES, _("see deliveries"))
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	return {
		"name": so.name,
		"customer_name": so.customer_name,
		"items": [
			{
				"so_detail": d.name,
				"item_code": d.item_code,
				"item_name": d.item_name,
				"uom": d.uom,
				"qty": flt(d.qty, 3),
				"pending": flt(d.qty - d.delivered_qty, 3),
			}
			for d in so.items
			if d.qty > d.delivered_qty
		],
	}


@frappe.whitelist()
def create_delivery_note(sales_order: str, entries):
	"""Delivery Note for what was weighed. entries = [{so_detail, qty}]; qty 0 leaves the item out."""
	require_role(DELIVERY_ROLES, _("create the Delivery Note"))
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	weighed = {e["so_detail"]: flt(e["qty"]) for e in frappe.parse_json(entries)}
	dn = make_delivery_note(sales_order)
	rows = [d for d in dn.items if weighed.get(d.so_detail, 0) > 0]
	if not rows:
		frappe.throw(_("Enter the weighed qty for at least one item."))
	for d in rows:
		d.qty = weighed[d.so_detail]
	dn.set("items", rows)
	dn.insert()
	dn.submit()
	return {"name": dn.name}


def build_invoice(delivery_note):
	"""Sales Invoice (not saved) from a Delivery Note, each rate filled from today's Item Price where there is one."""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	from chef_alarab.events.sales_invoice_price import apply_current_price

	if existing := invoice_of(delivery_note):
		frappe.throw(_("Sales Invoice {0} already exists for this Delivery Note.").format(existing))
	si = make_sales_invoice(delivery_note)
	apply_default_sales_taxes(si)  # an order made without a tax template would otherwise get 30% VAT
	apply_current_price(si)
	return si


@frappe.whitelist()
def get_invoice_preview(delivery_note: str):
	"""What the Sales Invoice would contain: each item with its qty and rate (Item Price, 0 when there is none)."""
	require_role(ACCOUNTS_ROLES, _("create the Sales Invoice"))
	si = build_invoice(delivery_note)
	return {
		"customer": si.customer_name,
		"items": [
			{
				"dn_detail": d.dn_detail,
				"item_code": d.item_code,
				"item_name": d.item_name,
				"qty": flt(d.qty, 3),
				"uom": d.uom,
				"rate": flt(d.rate),
			}
			for d in si.items
		],
	}


@frappe.whitelist()
def create_sales_invoice(delivery_note: str, rates=None):
	"""Draft Sales Invoice from a Delivery Note. rates = [{dn_detail, rate}] typed in the app win over Item Price.

	It stays a draft: Accounts checks it in ERPNext and submits."""
	require_role(ACCOUNTS_ROLES, _("create the Sales Invoice"))
	typed = {r["dn_detail"]: flt(r["rate"]) for r in frappe.parse_json(rates or "[]")}
	si = build_invoice(delivery_note)
	for d in si.items:
		if d.dn_detail in typed:
			d.price_list_rate = d.rate = typed[d.dn_detail]
			d.discount_percentage = d.discount_amount = 0
	si.insert()
	return {
		"name": si.name,
		"grand_total": flt(si.grand_total),
		"no_price": [d.item_name for d in si.items if not flt(d.rate)],
	}


@frappe.whitelist()
def get_sales_invoice(name: str):
	"""A Sales Invoice for the app: header, items with rate and amount, and the totals."""
	require_role(ACCOUNTS_ROLES, _("see the Sales Invoice"))
	si = frappe.get_doc("Sales Invoice", name)
	si.check_permission("read")
	return {
		"name": si.name,
		"customer": si.customer_name,
		"date": str(si.posting_date),
		"status": si.status,
		"docstatus": si.docstatus,
		"net_total": flt(si.net_total),
		"vat": flt(si.total_taxes_and_charges),
		"grand_total": flt(si.grand_total),
		"items": [
			{"item_name": d.item_name, "qty": flt(d.qty, 3), "uom": d.uom, "rate": flt(d.rate), "amount": flt(d.net_amount)}
			for d in si.items
		],
	}


@frappe.whitelist()
def sales_invoice_image(name: str):
	"""The Sales Invoice exactly as ERPNext prints it (print format + letterhead), as a PNG for the phone's gallery."""
	require_role(ACCOUNTS_ROLES, _("print the Sales Invoice"))
	si = frappe.get_doc("Sales Invoice", name)
	si.check_permission("read")
	frappe.local.response.filename = f"{si.name}.png"
	frappe.local.response.filecontent = pdf_to_png(frappe.get_print(si.doctype, si.name, doc=si, as_pdf=True))
	frappe.local.response.type = "download"
