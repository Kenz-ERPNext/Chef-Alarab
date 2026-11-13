# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Purchase Invoice: allow a different supplier than the sheet's "Market Purchase" receipt.

Goods are received at night against "Market Purchase"; the real suppliers are known in
the morning, and each one gets its own invoice linked to that receipt.
"""

import frappe

try:
	# kenz_trading also overrides Purchase Invoice (VAT rounding); keep its behaviour.
	from kenz_trading.overrides.purchase_invoice_override import CustomPurchaseInvoice as BaseInvoice
except ImportError:
	from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice as BaseInvoice


class PurchaseInvoice(BaseInvoice):
	def compare_values(self, ref_doc, fields, doc=None):
		if self.is_sheet_receipt(ref_doc.get("Purchase Receipt")):
			fields = [f for f in fields if f[0] != "supplier"]
		return super().compare_values(ref_doc, fields, doc)

	def is_sheet_receipt(self, receipts):
		"""All linked receipts were made by this invoice's Daily Purchase Sheet."""
		sheet = self.get("custom_daily_purchase_sheet")
		if not sheet or not receipts:
			return False
		sheets = frappe.get_all(
			"Purchase Receipt", filters={"name": ("in", receipts)}, pluck="custom_daily_purchase_sheet"
		)
		return len(sheets) == len(set(receipts)) and all(s == sheet for s in sheets)
