# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PurchaseRegion(Document):
	"""Market / region where goods are bought, e.g. Jeddah Haraj. Picked on the Purchase Invoice."""
