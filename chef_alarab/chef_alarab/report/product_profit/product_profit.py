# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Profit on what was sold: per product, per customer, per UOM.

Stock is not tracked, so ERPNext has no cost for a sale. Here the cost comes from purchases:
- Sales = submitted Sales Invoices in the period (net of VAT). The "Include Draft Sales" and
  "Include Draft Purchase" filters add draft Sales / Purchase Invoices.
- Cost rate = average of the item's last 2 Purchase Invoice rates (per stock unit, net of VAT)
  on or before the sale date.
- Cost = stock qty sold x cost rate, so every UOM (Box, Bag 20kg ...) is costed through the
  item's stock unit. Profit = Sales - Cost. Returns reduce the day they are posted.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, formatdate

LAST_PURCHASES = 2
PROFIT_PURCHASES = 2  # profit per UOM is also shown at each of the last 2 purchases


def execute(filters=None):
	filters = frappe._dict(filters or {})
	lines = get_sales_lines(filters)
	purchases = {}
	for d in lines:
		key = (d.item_code, d.posting_date)
		if key not in purchases:
			purchases[key] = last_purchase_rates(
				d.item_code, d.posting_date, filters.draft_purchase, filters.purchase_region
			)
		d.purchases = purchases[key]
		rates = [rate for _date, rate in d.purchases]
		d.cost_missing = not rates
		d.stock_rate = sum(rates) / len(rates) if rates else 0
		d.cost = flt(d.stock_qty) * d.stock_rate
		d.profit = flt(d.sales) - d.cost

	columns = get_columns()
	# Cells a row has no value for stay empty (otherwise they show 0.00).
	rows = [{**dict.fromkeys(c["fieldname"] for c in columns), **r} for r in get_rows(lines)]
	return columns, rows


def get_sales_lines(filters):
	conditions = [
		"si.docstatus < 2" if filters.draft_sales else "si.docstatus = 1",
		"si.company = %(company)s",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	if filters.customer:
		conditions.append("si.customer = %(customer)s")
	if filters.item_code:
		conditions.append("sii.item_code = %(item_code)s")
	if filters.sales_invoice:
		conditions.append("si.name = %(sales_invoice)s")
	return frappe.db.sql(
		f"""
		SELECT si.posting_date, si.customer_name, sii.item_code, sii.item_name, sii.uom,
			sii.qty, sii.stock_qty, sii.conversion_factor, sii.base_net_amount AS sales
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY sii.item_name, si.customer_name
		""",
		filters,
		as_dict=True,
	)


def last_purchase_rates(item_code, date, include_draft=False, region=None):
	"""The item's purchases on its last 2 purchase days as (date, rate per stock unit net of VAT), newest first.

	When several bills fall on one day, that day's rate is the one on the bill entered last.
	With a region, only bills from that Purchase Region count.
	"""
	rows = frappe.db.sql(
		"""
		SELECT pi.posting_date, pii.base_net_amount / pii.stock_qty
		FROM `tabPurchase Invoice Item` pii
		JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus IN %s AND pi.is_return = 0 AND pii.item_code = %s
			AND pi.posting_date <= %s AND pii.stock_qty > 0
			AND (%s IS NULL OR pi.custom_purchase_region = %s)
		ORDER BY pi.posting_date DESC, pi.creation DESC, pii.idx DESC
		LIMIT 100
		""",
		((0, 1) if include_draft else (1,), item_code, date, region or None, region or None),
	)
	per_day = {}
	for day, rate in rows:
		per_day.setdefault(day, flt(rate))  # rows are newest first: keep the day's last bill
	return list(per_day.items())[:LAST_PURCHASES]


def total_of(rows):
	t = {f: sum(flt(r[f]) for r in rows) for f in ("qty", "sales", "cost", "profit")}
	t["sales_rate"] = t["sales"] / t["qty"] if t["qty"] else None
	t["cost_rate"] = t["cost"] / t["qty"] if t["qty"] else None
	t["profit_pct"] = t["profit"] * 100 / t["cost"] if t["cost"] else None
	t["cost_missing"] = any(r.get("cost_missing") for r in rows)
	return t


def get_rows(lines):
	"""Product rows with each customer under them."""
	products = defaultdict(list)
	for d in lines:
		products[d.item_code].append(d)
	rows = []
	for items in products.values():
		uoms = {d.uom for d in items}
		product = total_of(items)
		if len(uoms) > 1:  # Box + Kg cannot be added up
			product.update({"qty": None, "sales_rate": None, "cost_rate": None})
		newest = max(items, key=lambda d: d.posting_date)
		rows.append(
			{
				**product,
				"name": items[0].item_name,
				"uom": next(iter(uoms)) if len(uoms) == 1 else _("Mixed"),
				# "12.00 (27-11) · 13.00 (26-11)": newest first, each with its purchase date.
				"last_rates": " · ".join(f"{r:,.2f} ({dt.strftime('%d-%m')})" for dt, r in newest.purchases)
				or _("Not bought"),
				**(purchase_profits(items, newest.purchases) if len(uoms) == 1 else {}),
				"indent": 0,
				"row_type": "product",
			}
		)
		customers = defaultdict(list)
		for d in items:
			customers[(d.customer_name, d.uom)].append(d)
		for (customer, uom), sold in customers.items():
			rows.append(
				{
					**total_of(sold),
					**purchase_profits(sold, newest.purchases),
					"name": customer,
					"uom": uom,
					"indent": 1,
					"row_type": "customer",
				}
			)
	return rows


def purchase_profits(sold, purchases):
	"""Profit per UOM had the cost been each of the last 2 purchase rates: "4.60 (27-11-2026)"."""
	qty = sum(flt(d.qty) for d in sold)
	if not qty:
		return {}
	sales_rate = sum(flt(d.sales) for d in sold) / qty
	cells = {}
	for i, (date, rate) in enumerate(purchases[:PROFIT_PURCHASES], 1):
		profit = sales_rate - rate * (flt(sold[0].conversion_factor) or 1)
		cells[f"purchase_profit_{i}"] = f"{profit:,.2f} ({formatdate(date)})"
		cells[f"purchase_loss_{i}"] = profit < 0
	return cells


def get_columns():
	def col(label, fieldname, fieldtype="Currency", width=110):
		return {"label": label, "fieldname": fieldname, "fieldtype": fieldtype, "width": width}

	return [
		col(_("Product / Customer"), "name", "Data", 240),
		col(_("UOM"), "uom", "Data", 90),
		col(_("Qty"), "qty", "Float", 80),
		col(_("Sales Rate"), "sales_rate"),
		col(_("Last 2 Purchase Rates"), "last_rates", "Data", 230),
		col(_("Profit/UOM · Last PI"), "purchase_profit_1", "Data", 170),
		col(_("Profit/UOM · 2nd Last PI"), "purchase_profit_2", "Data", 190),
	]
