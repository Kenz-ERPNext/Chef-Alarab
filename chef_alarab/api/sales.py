# Copyright (c) 2026, Chef Al Arab and contributors
"""Mobile API for taking a Sales Order: pick customer and items, create a new item when it is missing."""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from chef_alarab.api.accounts import apply_default_sales_taxes, get_company, pdf_to_png
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.daily_purchase_sheet import (
	ACCOUNTS_ROLES,
	require_role,
)

DEFAULT_GROUP = "Fruits and Vegetables"
DEFAULT_UOM = "Kg"
PAGE = 20  # rows per page of a search list; the app loads the next page on scroll


def like(query):
	return f"%{(query or '').strip()}%"


@frappe.whitelist()
def search_customers(query: str = "", start: int = 0, page_length: int = PAGE):
	require_role(ACCOUNTS_ROLES, _("take orders"))
	return frappe.get_list(
		"Customer",
		filters={"disabled": 0},
		or_filters={"name": ("like", like(query)), "customer_name": ("like", like(query))},
		fields=["name", "customer_name"],
		order_by="customer_name",
		limit_start=cint(start),
		limit_page_length=cint(page_length),
	)


@frappe.whitelist()
def search_items(query: str = "", start: int = 0, page_length: int = PAGE):
	"""Active items for sale, with the unit to order them in."""
	require_role(ACCOUNTS_ROLES, _("take orders"))
	return frappe.get_list(
		"Item",
		filters={"disabled": 0, "is_sales_item": 1},
		or_filters={"item_code": ("like", like(query)), "item_name": ("like", like(query))},
		fields=["item_code", "item_name", "stock_uom as uom"],
		order_by="item_name",
		limit_start=cint(start),
		limit_page_length=cint(page_length),
	)


@frappe.whitelist()
def search_uoms(query: str = "", start: int = 0, page_length: int = PAGE):
	require_role(ACCOUNTS_ROLES, _("take orders"))
	return frappe.get_list(
		"UOM",
		filters={"enabled": 1, "name": ("like", like(query))},
		fields=["name"],
		order_by="name",
		limit_start=cint(start),
		limit_page_length=cint(page_length),
	)


def next_item_code():
	"""FV-047 → FV-048: the site names items by hand, in one running series."""
	codes = frappe.get_all("Item", filters={"item_code": ("like", "FV-%")}, pluck="item_code")
	numbers = [int(m.group(1)) for c in codes if (m := re.fullmatch(r"FV-(\d+)", c))]
	return f"FV-{max(numbers, default=0) + 1:03d}"


def default_tax_template():
	"""Some sites require an item tax template on every item (custom field). Use the one most items have."""
	if not frappe.get_meta("Item").has_field("custom_item_tax_template"):
		return None
	rows = frappe.db.sql(
		"""SELECT custom_item_tax_template FROM `tabItem`
		WHERE IFNULL(custom_item_tax_template, '') != ''
		GROUP BY custom_item_tax_template ORDER BY COUNT(*) DESC LIMIT 1"""
	)
	return rows[0][0] if rows else None


@frappe.whitelist()
def create_item(item_name: str, uom: str = DEFAULT_UOM, item_group: str = DEFAULT_GROUP):
	"""New item the shop does not stock (Maintain Stock off), ready to order."""
	require_role(ACCOUNTS_ROLES, _("create items"))
	name = (item_name or "").strip()
	if not name:
		frappe.throw(_("Enter the item name."))
	existing = frappe.db.get_value("Item", {"item_name": name})
	if existing:
		frappe.throw(_("Item {0} already exists: {1}.").format(frappe.bold(name), existing))
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": next_item_code(),
			"item_name": name,
			"item_group": item_group,
			"stock_uom": uom,
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
		}
	)
	if tax_template := default_tax_template():
		item.custom_item_tax_template = tax_template
	item.insert()
	return {"item_code": item.item_code, "item_name": item.item_name, "uom": item.stock_uom}


@frappe.whitelist()
def create_sales_order(customer: str, delivery_date: str, items, submit: int = 1):
	"""Sales Order for the delivery date. items = [{item_code, qty}] in the item's own unit. No rate (set on the invoice)."""
	require_role(ACCOUNTS_ROLES, _("take orders"))
	lines = [d for d in frappe.parse_json(items) if flt(d.get("qty")) > 0]
	if not lines:
		frappe.throw(_("Add at least one item with a qty."))
	so = frappe.new_doc("Sales Order")
	so.update(
		{
			"customer": customer,
			"company": get_company(),
			"transaction_date": today(),
			"delivery_date": getdate(delivery_date),
		}
	)
	for d in lines:
		so.append(
			"items",
			{"item_code": d["item_code"], "qty": flt(d["qty"]), "delivery_date": getdate(delivery_date)},
		)
	apply_default_sales_taxes(so)
	so.insert()
	if int(submit):
		so.submit()
	return {"name": so.name, "docstatus": so.docstatus}


@frappe.whitelist()
def get_sales_order(name: str):
	"""A Sales Order for the app: who, when, how much was ordered and how much is delivered."""
	require_role(ACCOUNTS_ROLES, _("see Sales Orders"))
	so = frappe.get_doc("Sales Order", name)
	so.check_permission("read")
	return {
		"name": so.name,
		"customer": so.customer_name,
		"date": str(so.transaction_date),
		"delivery_date": str(so.delivery_date) if so.delivery_date else None,
		"docstatus": so.docstatus,
		"status": so.status,
		"per_delivered": flt(so.per_delivered),
		"items": [
			{
				"item_name": d.item_name,
				"qty": flt(d.qty, 3),
				"uom": d.uom,
				"delivered_qty": flt(d.delivered_qty, 3),
			}
			for d in so.items
		],
	}


@frappe.whitelist()
def sales_order_image(name: str):
	"""The Sales Order exactly as ERPNext prints it (print format + letterhead), as a PNG for the phone's gallery."""
	require_role(ACCOUNTS_ROLES, _("print the Sales Order"))
	so = frappe.get_doc("Sales Order", name)
	so.check_permission("read")
	frappe.local.response.filename = f"{so.name}.png"
	frappe.local.response.filecontent = pdf_to_png(frappe.get_print(so.doctype, so.name, doc=so, as_pdf=True))
	frappe.local.response.type = "download"
