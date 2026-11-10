# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class OutsideSale(Document):
	"""Sales made outside the system for one day. Report-only: no GL entries."""

	def autoname(self):
		self.name = f"OS-{self.sale_date}"

	def before_insert(self):
		self.validate_one_per_day()

	def validate(self):
		self.validate_one_per_day()

	def validate_one_per_day(self):
		existing = frappe.db.get_value(
			"Outside Sale",
			{"sale_date": self.sale_date, "company": self.company, "name": ("!=", self.name or "")},
		)
		if existing:
			frappe.throw(
				_("Outside Sale for this date already exists: {0}. Edit that one.").format(
					frappe.utils.get_link_to_form("Outside Sale", existing)
				)
			)


@frappe.whitelist()
def save_for_day(company, sale_date, amount, note=None):
	"""Called from the Daily Profit Summary report: create the day's entry, or update it."""
	name = frappe.db.get_value("Outside Sale", {"company": company, "sale_date": sale_date})
	if name:
		doc = frappe.get_doc("Outside Sale", name)
		doc.check_permission("write")
	else:
		doc = frappe.new_doc("Outside Sale")
		doc.update({"company": company, "sale_date": sale_date})
		doc.check_permission("create")
	doc.amount = frappe.utils.flt(amount)
	doc.note = note
	doc.save()
	return doc.name
