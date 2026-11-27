# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Purchases per Purchase Region (market): totals on top, a chart per region, then the invoices grouped by region."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

AMOUNTS = ("taxable", "tax", "total")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	invoices = get_invoices(filters)
	groups = defaultdict(list)
	for d in invoices:
		groups[d.region].append(d)
	return get_columns(), get_rows(groups), None, get_chart(groups), get_summary(invoices)


def get_invoices(filters):
	return frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"company": filters.company,
			"posting_date": ["between", [filters.from_date, filters.to_date]],
			"custom_purchase_region": filters.region or ["is", "set"],
		},
		fields=[
			"posting_date",
			"name as purchase_invoice",
			"custom_purchase_region as region",
			"supplier_name",
			"base_net_total as taxable",
			"base_total_taxes_and_charges as tax",
			"base_grand_total as total",
		],
		order_by="posting_date, name",
	)


def total_of(rows):
	return {f: sum(flt(r[f]) for r in rows) for f in AMOUNTS}


def get_rows(groups):
	"""Region row with its subtotal, its invoices indented under it; a grand total at the end."""
	rows = []
	for i, region in enumerate(sorted(groups)):
		invoices, color = groups[region], i % 5  # colour of the region in the table (see region_wise_purchase.js)
		rows.append(
			{
				"name": region,
				"indent": 0,
				"is_group": 1,
				"color": color,
				"bills": len(invoices),
				**total_of(invoices),
			}
		)
		rows += [{**d, "name": d.supplier_name, "indent": 1, "color": color} for d in invoices]
	if rows:
		every = [d for invoices in groups.values() for d in invoices]
		rows.append(
			{"name": _("Grand Total"), "indent": 0, "is_total": 1, "bills": len(every), **total_of(every)}
		)
	return rows


def get_columns():
	return [
		{"label": _("Vendor"), "fieldname": "name", "fieldtype": "Data", "width": 420},
		{"label": _("Bills"), "fieldname": "bills", "fieldtype": "Int", "width": 70},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Purchase Invoice"),
			"fieldname": "purchase_invoice",
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 160,
		},
		{"label": _("Taxable"), "fieldname": "taxable", "fieldtype": "Currency", "width": 140},
		{"label": _("VAT"), "fieldname": "tax", "fieldtype": "Currency", "width": 120},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 140},
	]


def get_chart(groups):
	if not groups:
		return None
	names = sorted(groups)
	return {
		"data": {
			"labels": names,
			"datasets": [{"name": _("Total"), "values": [total_of(groups[h])["total"] for h in names]}],
		},
		"type": "bar",
		"fieldtype": "Currency",
		"colors": ["#5e64ff"],
		"barOptions": {"spaceRatio": 0.5},
		"height": 220,
	}


def get_summary(invoices):
	if not invoices:
		return []
	t = total_of(invoices)
	return [
		{"label": _("Bills"), "value": len(invoices), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Taxable"), "value": t["taxable"], "datatype": "Currency", "indicator": "Grey"},
		{"label": _("VAT"), "value": t["tax"], "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Total"), "value": t["total"], "datatype": "Currency", "indicator": "Green"},
	]
