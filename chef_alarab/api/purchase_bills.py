# Copyright (c) 2026, Chef Al Arab and contributors
"""Mobile API for Purchase Invoices made from the Daily Purchase Sheet: view, correct the rates, submit, print."""

import frappe
from frappe import _
from frappe.utils import flt

from chef_alarab.api.accounts import pdf_to_png
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.daily_purchase_sheet import (
	ACCOUNTS_ROLES,
	require_role,
)


PRINT_FORMAT = "Purchase Bill"  # this app's format: letterhead, supplier, items, totals


def load(name):
	require_role(ACCOUNTS_ROLES, _("see Purchase Invoices"))
	doc = frappe.get_doc("Purchase Invoice", name)
	doc.check_permission("read")
	return doc


def details(doc):
	lines = [d.custom_dps_supplier_line for d in doc.items if d.get("custom_dps_supplier_line")]
	sheet = frappe.db.get_value("Daily Purchase Sheet Supplier Line", lines[0], "parent") if lines else None
	return {
		"name": doc.name,
		"supplier": doc.supplier_name or doc.supplier,
		"company": doc.company,
		"created_by": frappe.db.get_value("User", doc.owner, "full_name") or doc.owner,
		"date": str(doc.posting_date),
		"due_date": str(doc.due_date) if doc.due_date else None,
		"bill_no": doc.bill_no,
		"sheet": sheet,
		"status": doc.status,
		"docstatus": doc.docstatus,
		"total_qty": flt(doc.total_qty, 3),
		"net_total": flt(doc.net_total),
		"vat": flt(doc.total_taxes_and_charges),
		"grand_total": flt(doc.grand_total),
		"outstanding": flt(doc.outstanding_amount),
		"items": [
			{
				"row": d.name,
				"item_code": d.item_code,
				"item_name": d.item_name,
				"qty": flt(d.qty, 3),
				"uom": d.uom,
				"rate": flt(d.rate),
				"amount": flt(d.net_amount),
			}
			for d in doc.items
		],
	}


@frappe.whitelist()
def get_purchase_invoice(name: str):
	return details(load(name))


@frappe.whitelist()
def update_purchase_invoice_rates(name: str, rates):
	"""Correct the rate of draft invoice rows. rates = [{row, rate}]. A submitted invoice cannot be changed."""
	doc = load(name)
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft invoice can be changed."))
	typed = {r["row"]: flt(r["rate"]) for r in frappe.parse_json(rates)}
	for d in doc.items:
		if d.name in typed:
			d.rate = typed[d.name]
			d.price_list_rate = typed[d.name]
	doc.save()
	return details(doc)


@frappe.whitelist()
def submit_purchase_invoice(name: str):
	"""Approve the invoice: Accounts has checked it. The sheet's rules (rate must not be 0) apply."""
	doc = load(name)
	doc.submit()
	return details(doc)


@frappe.whitelist()
def purchase_invoice_image(name: str):
	"""The Purchase Invoice exactly as ERPNext prints it (print format + letterhead), as a PNG for the phone's gallery."""
	doc = load(name)
	frappe.local.response.filename = f"{doc.name}.png"
	frappe.local.response.filecontent = pdf_to_png(frappe.get_print(doc.doctype, doc.name, PRINT_FORMAT, doc=doc, as_pdf=True))
	frappe.local.response.type = "download"
