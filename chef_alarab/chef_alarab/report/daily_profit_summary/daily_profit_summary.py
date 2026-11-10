# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Per day: purchases, outside sales, system sales, total sales, profit, profit %.

- Total Purchase = submitted Purchase Invoices (net of VAT)
- System Sales   = submitted Sales Invoices (net of VAT)
- Outside Sale   = manual "Outside Sale" entry (sales without an invoice; not in accounts)
- Total Sales    = System Sales (+ Outside Sale when "Include Outside Sale" is ticked)
- Profit         = Total Sales - Total Purchase
- Profit %       = Profit x 100 / Total Purchase (markup on cost)
Returns / debit notes reduce the day they are posted.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date."))

	purchase = invoice_totals("Purchase Invoice", filters)
	system_sales = invoice_totals("Sales Invoice", filters)
	with_outside = bool(filters.include_outside_sale)
	outside, notes = outside_sales(filters) if with_outside else ({}, {})

	data = [
		make_row(day, purchase.get(day, 0), outside.get(day, 0), system_sales.get(day, 0), notes.get(day))
		for day in sorted(set(purchase) | set(system_sales) | set(outside))
	]
	total = None
	if data:
		total = make_row(None, *(sum(d[k] for d in data) for k in ("purchase", "outside_sale", "system_sales")))
		total.update({"label": _("Total"), "is_total": 1})

	return (
		get_columns(with_outside),
		data + ([total] if total else []),
		None,
		get_chart(data),
		get_summary(total, with_outside),
	)


def invoice_totals(doctype, filters):
	rows = frappe.get_all(
		doctype,
		filters={
			"docstatus": 1,
			"company": filters.company,
			"is_opening": "No",
			"posting_date": ["between", [filters.from_date, filters.to_date]],
		},
		fields=["posting_date", "sum(base_net_total) as amount"],
		group_by="posting_date",
	)
	return {r.posting_date: flt(r.amount) for r in rows}


def outside_sales(filters):
	rows = frappe.get_all(
		"Outside Sale",
		filters={"company": filters.company, "sale_date": ["between", [filters.from_date, filters.to_date]]},
		fields=["sale_date", "amount", "note"],
	)
	amounts, notes = defaultdict(float), {}
	for r in rows:
		amounts[r.sale_date] += flt(r.amount)
		if r.note:
			notes[r.sale_date] = r.note
	return amounts, notes


def make_row(day, purchase, outside, system_sales, note=None):
	total_sales = flt(outside) + flt(system_sales)
	profit = total_sales - flt(purchase)
	return {
		"date": day,
		"label": None,
		"purchase": flt(purchase),
		"outside_sale": flt(outside),
		"system_sales": flt(system_sales),
		"total_sales": total_sales,
		"profit": profit,
		"profit_pct": profit * 100 / purchase if purchase else 0,
		"note": note,
	}


def get_columns(with_outside):
	cur = {"fieldtype": "Currency", "width": 140}
	cols = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": "", "fieldname": "label", "fieldtype": "Data", "width": 60},
		{"label": _("Total Purchase"), "fieldname": "purchase", **cur},
	]
	if with_outside:
		cols.append({"label": _("Outside Sale"), "fieldname": "outside_sale", **cur})
	cols.append({"label": _("System Sales"), "fieldname": "system_sales", **cur})
	if with_outside:
		cols.append({"label": _("Total Sales"), "fieldname": "total_sales", **cur})
	cols += [
		{"label": _("Profit"), "fieldname": "profit", **cur},
		{"label": _("Profit %"), "fieldname": "profit_pct", "fieldtype": "Percent", "width": 100},
	]
	if with_outside:
		cols.append({"label": _("Note"), "fieldname": "note", "fieldtype": "Data", "width": 200})
	return cols


def get_chart(data):
	if not data:
		return None
	return {
		"data": {
			"labels": [frappe.format(d["date"], "Date") for d in data],
			"datasets": [
				{"name": _("Total Purchase"), "values": [d["purchase"] for d in data]},
				{"name": _("Sales"), "values": [d["total_sales"] for d in data]},
				{"name": _("Profit"), "values": [d["profit"] for d in data]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
		"colors": ["#F5A524", "#1E5631", "#2E8B57"],
	}


def get_summary(total, with_outside):
	if not total:
		return []
	good = "Green" if total["profit"] >= 0 else "Red"
	cards = [{"label": _("Total Purchase"), "value": total["purchase"], "datatype": "Currency", "indicator": "Orange"}]
	if with_outside:
		cards.append({"label": _("Outside Sale"), "value": total["outside_sale"], "datatype": "Currency", "indicator": "Grey"})
	cards.append({"label": _("System Sales"), "value": total["system_sales"], "datatype": "Currency", "indicator": "Blue"})
	if with_outside:
		cards.append({"label": _("Total Sales"), "value": total["total_sales"], "datatype": "Currency", "indicator": "Blue"})
	cards += [
		{"label": _("Profit"), "value": total["profit"], "datatype": "Currency", "indicator": good},
		{"label": _("Profit %"), "value": total["profit_pct"], "datatype": "Percent", "indicator": good},
	]
	return cards
