# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Purchase Invoices from Daily Purchase Sheet supplier lines.

Stock already came in through the sheet's Purchase Receipt (rate 0, supplier
"Market Purchase"), so these invoices use Update Stock = No. Each row is linked to
that receipt row: with Buying Settings "Set Landed Cost Based on Purchase Invoice
Rate" ERPNext moves the invoice rate into the receipt valuation and reposts, so
the Delivery Note cost (Gross Profit) gets the real purchase cost.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def make_invoices(sheet, line_names=None):
	if sheet.docstatus != 1:
		frappe.throw(_("Submit the sheet before creating Purchase Invoices."))
	frappe.has_permission("Purchase Invoice", "create", throw=True)

	on_invoice = lines_on_open_invoices(sheet)
	pending = [
		d
		for d in sheet.supplier_lines
		if not d.purchase_invoice
		and d.name not in on_invoice
		and (not line_names or d.name in line_names)
		and d.qty
	]
	if not pending:
		frappe.throw(_("No unbilled supplier lines. Lines already on a draft invoice are skipped."))

	by_supplier = defaultdict(list)
	for line in pending:
		by_supplier[line.supplier].append(line)

	return [make_invoice(sheet, supplier, lines) for supplier, lines in by_supplier.items()]


def make_invoice(sheet, supplier, lines):
	pi = frappe.new_doc("Purchase Invoice")
	pi.update(
		{
			"supplier": supplier,
			"company": sheet.company,
			"posting_date": frappe.utils.today(),
			"update_stock": 0,
			"custom_daily_purchase_sheet": sheet.name,
			"bill_no": next_bill_no(sheet.name),
			"bill_date": frappe.utils.today(),
			"remarks": _("Market purchase for delivery date {0} ({1})").format(
				frappe.format(sheet.purchase_date, "Date"), sheet.name
			),
		}
	)
	received = {d.item_code: d for d in sheet.items if d.purchase_receipt and d.pr_item}
	for line in lines:
		row = received.get(line.item_code)
		pi.append(
			"items",
			{
				"item_code": line.item_code,
				"qty": line.qty,
				"uom": line.uom,
				"conversion_factor": 1,
				"rate": line.rate,
				"purchase_receipt": row.purchase_receipt if row else None,
				"pr_detail": row.pr_item if row else None,
				"custom_dps_supplier_line": line.name,
			},
		)
	# Without a template ERPNext adds every account of the item tax template (Output + Input VAT).
	pi.taxes_and_charges = frappe.db.get_value(
		"Purchase Taxes and Charges Template", {"company": sheet.company, "is_default": 1, "disabled": 0}
	)
	pi.set_missing_values()
	if pi.taxes_and_charges:
		pi.set_taxes()
	pi.insert()
	return {"name": pi.name, "supplier": supplier, "grand_total": pi.grand_total}


def next_bill_no(sheet_name):
	"""Market suppliers give no bill number: DPS-2026-11-15-1, -2, ... per sheet."""
	n = frappe.db.count("Purchase Invoice", {"custom_daily_purchase_sheet": sheet_name}) + 1
	while frappe.db.exists("Purchase Invoice", {"bill_no": f"{sheet_name}-{n}"}):
		n += 1
	return f"{sheet_name}-{n}"


def lines_on_open_invoices(sheet):
	"""Supplier lines of this sheet already on a draft or submitted Purchase Invoice."""
	names = [d.name for d in sheet.supplier_lines]
	if not names:
		return set()
	return set(
		frappe.get_all(
			"Purchase Invoice Item",
			filters={"docstatus": ("<", 2), "custom_dps_supplier_line": ("in", names)},
			pluck="custom_dps_supplier_line",
		)
	)


# ---------- Purchase Invoice doc_events (hooks.py) ----------


def block_zero_rate(doc, method=None):
	"""A sheet invoice must carry the real supplier rate (it flows back to the sheet and profit)."""
	if not doc.get("custom_daily_purchase_sheet"):
		return
	missing = [f"#{d.idx} {d.item_code}" for d in doc.items if not flt(d.rate)]
	if missing:
		frappe.throw(_("Enter the supplier rate for {0}.").format(", ".join(missing)), title=_("Rate missing"))


def link_supplier_lines(doc, method=None):
	"""On PI submit: copy qty / rate to the sheet lines, link the invoice, refresh totals and status."""
	update_sheet(doc, doc.name)
	repost_now(doc)


def unlink_supplier_lines(doc, method=None):
	"""On PI cancel: clear the link so the lines can be billed again (rate is kept)."""
	update_sheet(doc, None)
	repost_now(doc)


def repost_now(doc):
	"""ERPNext queues the receipt repost and runs it hourly; run it now so profit is right today."""
	if not any(d.get("purchase_receipt") for d in doc.items):
		return
	frappe.enqueue(
		"erpnext.stock.doctype.repost_item_valuation.repost_item_valuation.repost_entries",
		queue="long",
		enqueue_after_commit=True,
		job_id="chef_alarab_repost_entries",
		deduplicate=True,
	)


def update_sheet(doc, invoice):
	if not doc.get("custom_daily_purchase_sheet"):
		return
	sheet = frappe.get_doc("Daily Purchase Sheet", doc.custom_daily_purchase_sheet)
	lines = {d.name: d for d in sheet.supplier_lines}
	for item in doc.items:
		line = lines.get(item.get("custom_dps_supplier_line"))
		if not line:
			continue
		line.purchase_invoice = invoice
		if invoice:
			# The invoice is the final word on what we bought and at what price (stock UOM).
			line.qty = flt(item.stock_qty)
			line.rate = flt(item.rate) / flt(item.conversion_factor or 1)
	sheet.calculate_totals()
	for row in sheet.supplier_lines + sheet.items:
		row.db_update()
	sheet.set_status()
	sheet.db_update()
