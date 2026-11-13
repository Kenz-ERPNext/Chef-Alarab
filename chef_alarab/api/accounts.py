# Copyright (c) 2026, Chef Al Arab and contributors
"""Mobile API for the Accountant / Admin screens: Orders, Purchase Sheet, Bills, Profit.

Thin wrappers over the Daily Purchase Sheet: its own methods and validations do the work,
so the app can never do more than the desk form allows.
"""

import os
import subprocess
import tempfile

import frappe
from frappe import _
from frappe.utils import flt, getdate

from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.daily_purchase_sheet import (
	ACCOUNTS_ROLES,
	require_role,
)
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.purchase_invoice import lines_on_open_invoices


def get_company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def apply_default_sales_taxes(doc):
	"""Same as picking the default Sales Taxes template in the form.

	Without a template ERPNext adds every account of the item tax template (Output + Input VAT = 30%)."""
	if doc.get("taxes_and_charges"):
		return
	template = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": doc.company, "is_default": 1, "disabled": 0}
	)
	if template:
		doc.taxes_and_charges = template
		doc.set("taxes", [])
		doc.set_taxes()


def default_warehouse(company):
	"""The site's default warehouse (Stock Settings), when it belongs to this company."""
	warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if warehouse and frappe.db.get_value("Warehouse", warehouse, "company") == company:
		return warehouse
	return None


def find_sheet(delivery_date):
	name = frappe.db.get_value(
		"Daily Purchase Sheet", {"purchase_date": getdate(delivery_date), "docstatus": ("<", 2)}
	)
	return frappe.get_doc("Daily Purchase Sheet", name) if name else None


def count_new_orders(doc):
	"""Sales Orders for this date that came in after the sheet was submitted (what "Add new orders" would pull in)."""
	if doc.docstatus != 1:
		return 0
	have = {d.sales_order for d in doc.sales_orders}
	return len({r.sales_order for r in doc.get_pending_so_items()} - have)


def sheet_summary(doc):
	return {
		"name": doc.name,
		"status": doc.status,
		"docstatus": doc.docstatus,
		"delivery_date": str(doc.purchase_date),
		"set_warehouse": doc.set_warehouse,
		"total_required_qty": flt(doc.total_required_qty, 3),
		"customers_count": len({d.customer for d in doc.sales_orders if d.customer}),
		"new_orders": count_new_orders(doc),
		"total_amount": flt(doc.total_amount),
		"items": [
			{
				"item_code": d.item_code,
				"item_name": d.item_name,
				"uom": d.uom,
				"required_qty": flt(d.required_qty, 3),
				"customer_breakdown": d.customer_breakdown,
				"assigned_to": d.assigned_to,
				"assigned_to_name": d.assigned_to_name,
				"ordered_qty": flt(d.ordered_qty, 3),
				"received_qty": flt(d.received_qty, 3),
			}
			for d in doc.items
		],
	}


# ---------- Orders ----------


@frappe.whitelist()
def get_orders(delivery_date: str):
	"""Sales Orders delivering on this date, one row per order."""
	require_role(ACCOUNTS_ROLES, _("see Sales Orders"))
	return frappe.db.sql(
		"""
		SELECT so.name, so.customer_name, c.customer_group, so.docstatus, so.status,
			COUNT(soi.name) AS items,
			SUM(soi.qty * soi.conversion_factor) AS qty
		FROM `tabSales Order` so
		JOIN `tabSales Order Item` soi ON soi.parent = so.name
		LEFT JOIN `tabCustomer` c ON c.name = so.customer
		WHERE so.docstatus < 2 AND so.status != 'Closed' AND soi.delivery_date = %s
		GROUP BY so.name
		ORDER BY so.customer_name
		""",
		getdate(delivery_date),
		as_dict=True,
	)


# ---------- Purchase Sheet ----------


@frappe.whitelist()
def get_sheet(delivery_date: str):
	"""The sheet of this date with its item rows, or null when none exists yet."""
	require_role(ACCOUNTS_ROLES, _("open the Purchase Sheet"))
	doc = find_sheet(delivery_date)
	return sheet_summary(doc) if doc else None


@frappe.whitelist()
def get_staff():
	"""Users who can be given items to buy."""
	require_role(ACCOUNTS_ROLES, _("see staff"))
	users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", ["Purchase User", "Purchase Manager"]), "parenttype": "User"},
		pluck="parent",
	)
	return frappe.get_all(
		"User",
		filters={
			"name": ("in", [u for u in users if u != "Administrator"] or [""]),
			"enabled": 1,
			"user_type": "System User",
		},
		fields=["name as id", "full_name"],
		order_by="full_name",
	)


@frappe.whitelist()
def create_sheet(delivery_date: str):
	"""New draft sheet for the date, filled with that day's Sales Order items."""
	require_role(ACCOUNTS_ROLES, _("create the Purchase Sheet"))
	doc = frappe.new_doc("Daily Purchase Sheet")
	company = get_company()
	doc.update({"purchase_date": getdate(delivery_date), "company": company, "set_warehouse": default_warehouse(company)})
	doc.get_items_from_sales_orders()
	doc.insert()
	return sheet_summary(doc)


@frappe.whitelist()
def submit_sheet(sheet: str):
	require_role(ACCOUNTS_ROLES, _("submit the Purchase Sheet"))
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	doc.submit()
	return sheet_summary(doc)


@frappe.whitelist()
def add_new_orders(sheet: str):
	"""Pull Sales Orders that came in after the sheet was submitted."""
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	doc.add_new_orders()
	return sheet_summary(doc)


@frappe.whitelist()
def assign_staff(sheet: str, item_codes, user: str):
	"""Give these items to one staff member (works on draft and submitted sheets)."""
	require_role(ACCOUNTS_ROLES, _("assign staff"))
	codes = set(frappe.parse_json(item_codes))
	if not frappe.db.get_value("User", {"name": user, "enabled": 1}):
		frappe.throw(_("User {0} is not active.").format(user))
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	for row in doc.items:
		if row.item_code in codes:
			row.assigned_to = user
	doc.save()
	return sheet_summary(doc)


PRINT_FORMAT = "Purchase List"


def pdf_to_png(pdf):
	"""All pages of a PDF as one tall PNG (pages stacked top to bottom). Needs poppler's pdftoppm."""
	from PIL import Image

	with tempfile.TemporaryDirectory() as folder:
		source = os.path.join(folder, "page.pdf")
		with open(source, "wb") as f:
			f.write(pdf)
		try:
			subprocess.run(
				["pdftoppm", "-png", "-r", "110", source, os.path.join(folder, "p")],
				capture_output=True,
				timeout=90,
				check=True,
			)
		except (FileNotFoundError, subprocess.CalledProcessError):
			frappe.throw(_("Could not make the picture. Install poppler-utils (pdftoppm) on the server."))
		pages = [Image.open(os.path.join(folder, n)).convert("RGB") for n in sorted(os.listdir(folder)) if n.endswith(".png")]
		sheet = Image.new("RGB", (max(p.width for p in pages), sum(p.height for p in pages)), "white")
		top = 0
		for p in pages:
			sheet.paste(p, (0, top))
			top += p.height
		out = os.path.join(folder, "all.png")
		sheet.save(out, optimize=True)
		with open(out, "rb") as f:
			return f.read()


@frappe.whitelist()
def purchase_list_image(sheet: str):
	"""The Purchase List exactly as ERPNext prints it (print format + letterhead), as a PNG for the phone's gallery."""
	require_role(ACCOUNTS_ROLES, _("print the Purchase List"))
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	doc.check_permission("read")
	pdf = frappe.get_print(doc.doctype, doc.name, PRINT_FORMAT, doc=doc, as_pdf=True)
	frappe.local.response.filename = f"{doc.name}.png"
	frappe.local.response.filecontent = pdf_to_png(pdf)
	frappe.local.response.type = "download"


# ---------- Supplier lines and bills ----------


@frappe.whitelist()
def save_supplier_line(sheet: str, item_code: str, supplier: str, qty: float, rate: float):
	"""Add or update what was bought: one line per item and supplier."""
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	line = next((d for d in doc.supplier_lines if d.item_code == item_code and d.supplier == supplier), None)
	if not line:
		row = next((d for d in doc.items if d.item_code == item_code), None)
		if not row:
			frappe.throw(_("Item {0} is not in this sheet.").format(item_code))
		line = doc.append("supplier_lines", {"item_code": item_code, "supplier": supplier, "uom": row.uom})
	elif line.name in lines_on_open_invoices(doc):
		frappe.throw(_("This line is on a draft Purchase Invoice. Delete that invoice first."))
	line.qty, line.rate = flt(qty), flt(rate)
	doc.save()
	return sheet_summary(doc)


@frappe.whitelist()
def get_bills(sheet: str):
	"""Supplier lines grouped by supplier. A line on a draft invoice counts as billed: only lines with no invoice are still to bill."""
	require_role(ACCOUNTS_ROLES, _("see supplier bills"))
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	names = [d.name for d in doc.supplier_lines] or [""]
	on_invoice = {
		r.line: r.parent
		for r in frappe.get_all(
			"Purchase Invoice Item",
			filters={"docstatus": ("<", 2), "custom_dps_supplier_line": ("in", names)},
			fields=["custom_dps_supplier_line as line", "parent"],
		)
	}
	suppliers = {}
	for d in doc.supplier_lines:
		invoice = d.purchase_invoice or on_invoice.get(d.name)
		s = suppliers.setdefault(
			d.supplier, {"supplier": d.supplier, "total": 0, "to_bill": 0, "invoices": set(), "lines": []}
		)
		s["total"] += flt(d.amount)
		if invoice:
			s["invoices"].add(invoice)
		else:
			s["to_bill"] += 1
		s["lines"].append(
			{
				"name": d.name,
				"item_code": d.item_code,
				"item_name": d.item_name,
				"qty": flt(d.qty, 3),
				"rate": flt(d.rate),
				"amount": flt(d.amount),
				"purchase_invoice": invoice,
			}
		)
	rows = list(suppliers.values())
	drafts = {
		r.name
		for r in frappe.get_all("Purchase Invoice", filters={"name": ("in", list({i for s in rows for i in s["invoices"]}) or [""]), "docstatus": 0}, fields=["name"])
	}
	for s in rows:
		s["drafts"] = len(set(s["invoices"]) & drafts)  # invoices still to be checked and submitted
		s["invoices"] = sorted(s["invoices"])
	return {"sheet": doc.name, "status": doc.status, "suppliers": rows}


@frappe.whitelist()
def create_invoices(sheet: str, line_names=None):
	"""Draft Purchase Invoice per supplier from the unbilled lines."""
	doc = frappe.get_doc("Daily Purchase Sheet", sheet)
	return doc.create_purchase_invoices(line_names)


# ---------- Profit ----------


@frappe.whitelist()
def get_profit(from_date: str, to_date: str, include_outside_sale: int = 0):
	"""Daily Profit Summary rows for the app (same numbers as the desk report)."""
	require_role(ACCOUNTS_ROLES, _("see profit"))
	from chef_alarab.chef_alarab.report.daily_profit_summary.daily_profit_summary import execute

	_columns, data, _msg, _chart, summary = execute(
		{
			"company": get_company(),
			"from_date": from_date,
			"to_date": to_date,
			"include_outside_sale": int(include_outside_sale),
		}
	)
	return {"rows": data, "summary": summary}
