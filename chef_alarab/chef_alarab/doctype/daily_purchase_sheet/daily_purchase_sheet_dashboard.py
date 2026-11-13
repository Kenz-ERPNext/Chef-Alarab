from frappe import _


def get_data():
	"""Connections tab: the orders on the sheet, and the receipts / invoices made from it."""
	return {
		"fieldname": "custom_daily_purchase_sheet",
		"internal_links": {"Sales Order": ["sales_orders", "sales_order"]},
		"transactions": [
			{"label": _("Selling"), "items": ["Sales Order"]},
			{"label": _("Buying"), "items": ["Purchase Receipt", "Purchase Invoice"]},
		],
	}
