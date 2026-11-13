# Copyright (c) 2026, Chef Al Arab and contributors
"""Daily Purchase Sheet receipt flow: "Market Purchase" supplier and Buying Settings.

Goods are received at night at rate 0 against "Market Purchase"; the Purchase Invoice
rate (morning) must update that receipt's valuation, so landed cost follows the invoice
rate and the PO/PR rate does not have to match it.
"""

import frappe

from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.purchase_receipt import MARKET_SUPPLIER


def execute():
	frappe.db.set_single_value(
		"Buying Settings", {"set_landed_cost_based_on_purchase_invoice_rate": 1, "maintain_same_rate": 0}
	)
	if frappe.db.exists("Supplier", MARKET_SUPPLIER):
		return
	group = frappe.db.get_single_value("Buying Settings", "supplier_group") or frappe.db.get_value(
		"Supplier Group", {"is_group": 0}
	)
	frappe.get_doc(
		{"doctype": "Supplier", "supplier_name": MARKET_SUPPLIER, "supplier_group": group, "supplier_type": "Company"}
	).insert(ignore_permissions=True)
