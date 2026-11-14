# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""API for the mobile app (Kenz Fresh). Logged-in users only."""

import frappe
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

# Steps on the Home progress bar.
STEP_ORDERS, STEP_PURCHASE, STEP_RECEIVE, STEP_DELIVER, STEP_DONE = range(5)


@frappe.whitelist()
def get_home(delivery_date: str | None = None):
	"""Numbers for the Home screen of one delivery date.

	Orders come in at night for the next morning, so by default: before noon = today, after = tomorrow.
	Only totals are returned (no prices), so every app user may see them.
	"""
	date = getdate(delivery_date) if delivery_date else default_delivery_date()
	orders = get_orders(date)
	sheet = frappe.db.get_value(
		"Daily Purchase Sheet",
		{"purchase_date": date, "docstatus": ("<", 2)},
		["name", "status", "docstatus"],
		as_dict=True,
	)
	rows = get_sheet_rows(sheet.name) if sheet else []
	user = frappe.session.user
	mine = [r for r in rows if r.assigned_to == user]
	to_buy, unit, items_left = qty_to_buy(orders, rows)

	return {
		"delivery_date": str(date),
		"sheet": sheet.name if sheet else None,
		"sheet_status": sheet.status if sheet else None,
		"sheet_items": len(rows),
		"unassigned": sum(1 for r in rows if not r.assigned_to),
		"orders": {"submitted": orders.submitted, "total": orders.total},
		"qty_to_buy": flt(to_buy, 3),
		"qty_unit": unit,
		"items_to_buy": items_left,
		"deliveries": {"done": orders.delivered, "total": orders.submitted},
		"step": get_step(sheet, rows, orders),
		"my_items": {"total": len(mine), "done": sum(1 for r in mine if r.supplier_lines)},
		"to_receive": sum(1 for r in rows if not flt(r.received_qty)),
		"to_bill": cint(
			frappe.db.count(
				"Daily Purchase Sheet Supplier Line",
				{"parent": sheet.name, "purchase_invoice": ("is", "not set")},
			)
			if sheet
			else 0
		),
	}


def qty_to_buy(orders, rows):
	"""What is still to be bought: qty, its unit (None when the items use different units), and how many items.

	With a sheet: per item, required minus bought (an item bought in excess does not cancel another item).
	Without one: everything ordered and not delivered yet."""
	if rows:
		left = [max(0, flt(r.required_qty) - flt(r.ordered_qty)) for r in rows]
		qty, count = sum(left), sum(1 for x in left if x > 0)
		units = {r.uom for r in rows}
	else:
		qty, count = orders.pending_qty, 0
		units = {orders.uom} if orders.uoms == 1 else set()
	return qty, (next(iter(units)) if len(units) == 1 else None), count


def default_delivery_date():
	return getdate(today()) if now_datetime().hour < 12 else getdate(add_days(today(), 1))


def get_orders(date):
	"""Sales Orders delivering on this date: count, submitted, delivered, qty still to deliver."""
	row = frappe.db.sql(
		"""
		SELECT
			COUNT(DISTINCT so.name) AS total,
			COUNT(DISTINCT IF(so.docstatus = 1, so.name, NULL)) AS submitted,
			COUNT(DISTINCT IF(so.docstatus = 1 AND so.per_delivered >= 100, so.name, NULL)) AS delivered,
			SUM(IF(so.docstatus = 1, (soi.qty - soi.delivered_qty), 0)) AS pending_qty,
			COUNT(DISTINCT soi.uom) AS uoms,
			MAX(soi.uom) AS uom
		FROM `tabSales Order` so
		JOIN `tabSales Order Item` soi ON soi.parent = so.name
		WHERE so.docstatus < 2 AND soi.delivery_date = %s AND so.status != 'Closed'
		""",
		date,
		as_dict=True,
	)[0]
	return frappe._dict({k: v if k == "uom" else flt(v) if k == "pending_qty" else cint(v) for k, v in row.items()})


def get_sheet_rows(sheet):
	rows = frappe.get_all(
		"Daily Purchase Sheet Item",
		filters={"parent": sheet},
		fields=["item_code", "assigned_to", "received_qty", "required_qty", "ordered_qty", "uom"],
	)
	with_supplier = set(
		frappe.get_all("Daily Purchase Sheet Supplier Line", filters={"parent": sheet}, pluck="item_code")
	)
	for r in rows:
		r.supplier_lines = r.item_code in with_supplier
	return rows


def get_step(sheet, rows, orders):
	"""Where the day is: orders → purchase → receive → deliver → done."""
	if orders.submitted and orders.delivered >= orders.submitted:
		return STEP_DONE
	if orders.delivered or (rows and all(flt(r.received_qty) for r in rows)):
		return STEP_DELIVER
	if sheet and sheet.docstatus == 1:
		return STEP_RECEIVE if any(flt(r.received_qty) for r in rows) else STEP_PURCHASE
	return STEP_ORDERS
