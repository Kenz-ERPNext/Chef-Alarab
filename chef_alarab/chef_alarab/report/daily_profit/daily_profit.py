# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Profit per Sales Invoice / Item / Customer for market purchases.

Stock is kept at zero value (periodic inventory), so ERPNext's Gross Profit report has no
cost. Here the cost of an item is the average purchase rate of that day's Daily Purchase
Sheet (net amount of the submitted Purchase Invoice when billed, else the supplier line).
Item view also shows what was bought vs sold, so short / waste shows up as lost cost.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	sheets = get_sheets(filters)
	if not sheets:
		return get_columns(filters), []
	cost = get_cost_rates(sheets)
	lines = get_invoice_lines(sheets)
	for d in lines:
		rate, missing = cost.get((d.sheet, d.item_code), (0, True))
		d.cost_rate = rate
		d.cost_missing = missing
		d.cost_amount = flt(d.qty) * rate
	return get_columns(filters), group(lines, filters, cost)


def get_sheets(filters):
	conditions = {"docstatus": 1, "purchase_date": ["between", [filters.from_date, filters.to_date]]}
	if filters.daily_purchase_sheet:
		conditions["name"] = filters.daily_purchase_sheet
	return frappe.get_all("Daily Purchase Sheet", filters=conditions, pluck="name")


def get_cost_rates(sheets):
	"""(sheet, item) -> (avg net purchase rate, cost_missing). Also keeps bought qty / amount."""
	rows = frappe.db.sql(
		"""
		SELECT l.parent AS sheet, l.item_code, l.qty, l.amount,
			pii.base_net_amount AS billed_amount, pii.stock_qty AS billed_qty
		FROM `tabDaily Purchase Sheet Supplier Line` l
		LEFT JOIN `tabPurchase Invoice Item` pii
			ON pii.custom_dps_supplier_line = l.name AND pii.docstatus = 1
		WHERE l.parent IN %(sheets)s
		""",
		{"sheets": tuple(sheets)},
		as_dict=True,
	)
	qty, amount, missing = defaultdict(float), defaultdict(float), defaultdict(bool)
	for r in rows:
		key = (r.sheet, r.item_code)
		billed = r.billed_amount is not None
		qty[key] += flt(r.billed_qty if billed else r.qty)
		amount[key] += flt(r.billed_amount if billed else r.amount)
		if not flt(r.billed_amount if billed else r.amount):
			missing[key] = True
	result = {k: (amount[k] / qty[k] if qty[k] else 0, missing[k] or not qty[k]) for k in qty}
	result["_bought"] = {k: (qty[k], amount[k]) for k in qty}
	return result


def get_invoice_lines(sheets):
	"""Submitted Sales Invoice lines of the Sales Orders on these sheets (net of VAT, stock UOM)."""
	return frappe.db.sql(
		"""
		SELECT dso.parent AS sheet, si.name AS invoice, si.posting_date, si.customer,
			sii.item_code, sii.item_name, sii.stock_qty AS qty, sii.stock_uom AS uom,
			sii.base_net_amount AS sales_amount
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1 AND si.is_return = 0
		JOIN `tabDaily Purchase Sheet SO` dso ON dso.sales_order = sii.sales_order
		WHERE dso.parent IN %(sheets)s
		ORDER BY si.posting_date, si.name, sii.idx
		""",
		{"sheets": tuple(sheets)},
		as_dict=True,
	)


def group(lines, filters, cost):
	by = filters.group_by or "Invoice"
	key_of = {
		"Invoice": lambda d: d.invoice,
		"Item": lambda d: (d.sheet, d.item_code),
		"Customer": lambda d: d.customer,
	}[by]
	out = {}
	for d in lines:
		k = key_of(d)
		row = out.setdefault(
			k,
			frappe._dict(
				invoice=d.invoice if by == "Invoice" else None,
				posting_date=d.posting_date if by == "Invoice" else None,
				customer=d.customer if by != "Item" else None,
				sheet=d.sheet if by != "Customer" else None,
				item_code=d.item_code if by == "Item" else None,
				item_name=d.item_name if by == "Item" else None,
				uom=d.uom if by == "Item" else None,
				qty=0,
				sales_amount=0,
				cost_amount=0,
				cost_missing=False,
			),
		)
		row.qty += flt(d.qty)
		row.sales_amount += flt(d.sales_amount)
		row.cost_amount += flt(d.cost_amount)
		row.cost_missing = row.cost_missing or d.cost_missing

	rows = list(out.values())
	for row in rows:
		if by == "Item":
			# Real cost of the day = everything bought (incl. short / waste), not only what was sold.
			bought_qty, bought_amount = cost.get("_bought", {}).get((row.sheet, row.item_code), (0, 0))
			row.bought_qty = bought_qty
			row.cost_amount = bought_amount
			row.cost_rate = bought_amount / bought_qty if bought_qty else 0
		row.profit = row.sales_amount - row.cost_amount
		row.profit_pct = row.profit / row.sales_amount * 100 if row.sales_amount else 0
	return rows


def get_columns(filters):
	by = filters.get("group_by") or "Invoice"
	cur = {"fieldtype": "Currency", "width": 120}
	cols = []
	if by == "Invoice":
		cols += [
			{"label": _("Sales Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
			{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		]
	if by != "Item":
		cols.append({"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 220})
	if by == "Item":
		cols += [
			{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 110},
			{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
			{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
			{"label": _("Bought Qty"), "fieldname": "bought_qty", "fieldtype": "Float", "width": 100},
			{"label": _("Avg Buy Rate"), "fieldname": "cost_rate", **cur},
		]
	if by != "Customer":
		cols.append({"label": _("Sheet"), "fieldname": "sheet", "fieldtype": "Link", "options": "Daily Purchase Sheet", "width": 140})
	cols += [
		{"label": _("Sold Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Sales (net)"), "fieldname": "sales_amount", **cur},
		{"label": _("Purchase Cost"), "fieldname": "cost_amount", **cur},
		{"label": _("Profit"), "fieldname": "profit", **cur},
		{"label": _("Profit %"), "fieldname": "profit_pct", "fieldtype": "Percent", "width": 90},
	]
	return cols
