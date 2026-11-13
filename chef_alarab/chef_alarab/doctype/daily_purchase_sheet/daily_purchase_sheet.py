# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


ACCOUNTS_ROLES = {"Accounts User", "Accounts Manager", "System Manager"}
STOCK_ROLES = {"Stock User", "Stock Manager", "System Manager"}


def require_role(roles, action):
	if not roles.intersection(frappe.get_roles()):
		frappe.throw(_("You are not allowed to {0}.").format(action), frappe.PermissionError)


class DailyPurchaseSheet(Document):
	"""One sheet per delivery date: what to buy tonight, who buys it, what arrived, what was billed."""

	def autoname(self):
		# DPS-2026-11-12; a cancelled sheet keeps its name, so a new one for that date gets -1, -2 ...
		base = f"DPS-{self.purchase_date}"
		name, n = base, 0
		while frappe.db.exists("Daily Purchase Sheet", name):
			n += 1
			name = f"{base}-{n}"
		self.name = name

	def before_insert(self):
		# Runs before naming, so the user sees this instead of "Duplicate Name".
		self.validate_one_sheet_per_day()

	def validate(self):
		self.validate_one_sheet_per_day()
		self.validate_duplicate_items()
		self.validate_duplicate_sales_orders()
		self.validate_supplier_lines()
		self.calculate_totals()
		self.set_status()

	def before_update_after_submit(self):
		# Staff add supplier lines / received qty after submit (allow_on_submit fields).
		self.validate_rows_unchanged()
		self.validate_billed_lines_unchanged()
		self.validate_duplicate_items()
		self.validate_supplier_lines()
		self.calculate_totals()
		self.set_status()

	def before_submit(self):
		if not self.items:
			frappe.throw(_("No items to buy. Pick a Delivery Date that has Sales Orders."))
		# Purchase / Stock users have "submit" only so they can save rows after submit
		# (Frappe needs it for update-after-submit). Submitting the plan is for Accounts.
		require_role(ACCOUNTS_ROLES, _("submit the Daily Purchase Sheet"))

	def on_submit(self):
		self.set_status(update=True)

	def before_cancel(self):
		billed = [d.purchase_invoice for d in self.supplier_lines if d.purchase_invoice]
		if billed:
			frappe.throw(
				_("Cancel Purchase Invoices {0} before cancelling this sheet.").format(", ".join(set(billed)))
			)

	def on_cancel(self):
		self.set_status(update=True)

	# ---------- Buttons ----------

	@frappe.whitelist()
	def get_items_from_sales_orders(self):
		"""Fill the sheet with pending qty of all submitted SOs for this delivery date, totalled per item.

		Called from the form when the Delivery Date is picked; the form shows the rows, the user saves.
		"""
		require_role(ACCOUNTS_ROLES, _("get items from Sales Orders"))
		if self.docstatus != 0:
			frappe.throw(_("Items can only be fetched while the sheet is in Draft."))
		if not self.purchase_date or not self.company:
			return {"items": 0, "sales_orders": 0}

		rows = self.get_pending_so_items()

		# Keep the staff already assigned when fetching again.
		previous = {(d.item_code, d.uom): d for d in self.items}
		totals = defaultdict(float)
		by_customer = defaultdict(lambda: defaultdict(float))
		names = {}
		for r in rows:
			key = (r.item_code, r.stock_uom)
			totals[key] += r.pending_qty
			by_customer[key][r.customer_name] += r.pending_qty
			names[key] = r.item_name

		self.set("items", [])
		for key in sorted(totals, key=lambda k: names[k]):
			old = previous.get(key)
			self.append(
				"items",
				{
					"item_code": key[0],
					"item_name": names[key],
					"uom": key[1],
					"required_qty": flt(totals[key], 3),
					"customer_breakdown": " · ".join(
						f"{c} {flt(q, 3):g}" for c, q in by_customer[key].items()
					),
					"assigned_to": old.assigned_to if old else None,
				},
			)

		self.set("sales_orders", [])
		for so in sorted({r.sales_order for r in rows}):
			self.append("sales_orders", {"sales_order": so})

		# Unsaved rows: the form gives them local names and inserts them on save.
		for d in self.items + self.sales_orders:
			d.set("__islocal", 1)
		self.calculate_totals()
		return {"items": len(self.items), "sales_orders": len(self.sales_orders)}

	@frappe.whitelist()
	def add_new_orders(self):
		"""Submitted sheet: pull Sales Orders that came in later for the same date (e.g. a morning order).

		Existing rows keep staff, supplier lines and received qty; only Required Qty and the
		customer breakdown are recalculated. New items get a new row.
		"""
		require_role(ACCOUNTS_ROLES, _("add new orders"))
		if self.docstatus != 1:
			frappe.throw(_("Use Get Items from Sales Orders while the sheet is in Draft."))
		frappe.has_permission("Daily Purchase Sheet", "submit", doc=self, throw=True)

		new_orders = {r.sales_order for r in self.get_pending_so_items()} - {
			d.sales_order for d in self.sales_orders
		}
		if not new_orders:
			frappe.throw(_("No new Sales Orders for this date."))

		for so in sorted(new_orders):
			self.append("sales_orders", {"sales_order": so})

		totals, breakdown, names = self.summarise_orders([d.sales_order for d in self.sales_orders])
		rows = {(d.item_code, d.uom): d for d in self.items}
		new_items = 0
		for key in sorted(totals, key=lambda k: names[k]):
			row = rows.get(key)
			if not row:
				row = self.append("items", {"item_code": key[0], "item_name": names[key], "uom": key[1]})
				new_items += 1
			row.required_qty = flt(totals[key], 3)
			row.customer_breakdown = breakdown[key]

		self.flags.adding_orders = True
		self.save()
		return {"sales_orders": len(new_orders), "new_items": new_items}

	def summarise_orders(self, sales_orders):
		"""Ordered qty (stock UOM) per item for the given Sales Orders, with customer breakdown."""
		rows = frappe.db.sql(
			"""
			SELECT soi.item_code, soi.item_name, soi.stock_uom, so.customer_name,
				soi.qty * soi.conversion_factor AS qty
			FROM `tabSales Order Item` soi
			JOIN `tabSales Order` so ON so.name = soi.parent
			WHERE so.name IN %(orders)s AND soi.delivery_date = %(date)s
			""",
			{"orders": tuple(sales_orders), "date": self.purchase_date},
			as_dict=True,
		)
		totals, by_customer, names = defaultdict(float), defaultdict(lambda: defaultdict(float)), {}
		for r in rows:
			key = (r.item_code, r.stock_uom)
			totals[key] += r.qty
			by_customer[key][r.customer_name] += r.qty
			names[key] = r.item_name
		breakdown = {
			key: " · ".join(f"{c} {flt(q, 3):g}" for c, q in custs.items()) for key, custs in by_customer.items()
		}
		return totals, breakdown, names

	@frappe.whitelist()
	def create_purchase_receipt(self):
		"""Goods arrived: Purchase Receipt for Received Qty at rate 0 (rate comes with the PI)."""
		require_role(STOCK_ROLES, _("create the Purchase Receipt"))
		from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.purchase_receipt import make_purchase_receipt

		return make_purchase_receipt(self)

	@frappe.whitelist()
	def create_purchase_invoices(self, line_names=None):
		"""Draft Purchase Invoice per supplier from unbilled supplier lines (Update Stock = No)."""
		require_role(ACCOUNTS_ROLES, _("create Purchase Invoices"))
		from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.purchase_invoice import make_invoices

		return make_invoices(self, frappe.parse_json(line_names) if line_names else None)

	def get_pending_so_items(self):
		"""Open SO lines for this date and company, not yet in another active sheet. Qty in stock UOM."""
		return frappe.db.sql(
			"""
			SELECT soi.item_code, soi.item_name, soi.stock_uom, so.name AS sales_order,
				so.customer_name,
				(soi.qty - soi.delivered_qty) * soi.conversion_factor AS pending_qty
			FROM `tabSales Order Item` soi
			JOIN `tabSales Order` so ON so.name = soi.parent
			WHERE so.docstatus = 1
				AND so.company = %(company)s
				AND soi.delivery_date = %(date)s
				AND so.status NOT IN ('Closed', 'On Hold', 'Completed')
				AND soi.qty > soi.delivered_qty
				AND so.name NOT IN (
					SELECT dso.sales_order FROM `tabDaily Purchase Sheet SO` dso
					JOIN `tabDaily Purchase Sheet` dps ON dps.name = dso.parent
					WHERE dps.docstatus < 2 AND dps.name != %(sheet)s
				)
			ORDER BY soi.item_name, so.customer_name
			""",
			{"company": self.company, "date": self.purchase_date, "sheet": self.name or ""},
			as_dict=True,
		)

	# ---------- Validations ----------

	def validate_one_sheet_per_day(self):
		# Not a DB unique key, so a cancelled sheet can be amended for the same date.
		existing = frappe.db.get_value(
			"Daily Purchase Sheet",
			{"purchase_date": self.purchase_date, "docstatus": ("<", 2), "name": ("!=", self.name or "")},
		)
		if existing:
			frappe.throw(
				_("A sheet for this date already exists: {0}. Open it, or delete it if it is a mistake.").format(
					frappe.utils.get_link_to_form("Daily Purchase Sheet", existing)
				)
			)

	def validate_rows_unchanged(self):
		"""After submit, item rows can be edited but not added, removed or swapped to another item."""
		before = self.get_doc_before_save()
		if not before:
			return
		old = {d.name: (d.item_code, d.uom) for d in before.items}
		new = {d.name: (d.item_code, d.uom) for d in self.items}
		if self.flags.adding_orders:
			# "Add New Orders" may append rows; existing rows must stay as they were.
			new = {k: v for k, v in new.items() if k in old}
		if old != new:
			frappe.throw(_("Items cannot be added, removed or changed after submit. Cancel and amend the sheet."))

		if self.flags.adding_orders:
			return
		# Required Qty and Sales Orders change only through "Add New Orders".
		if {d.sales_order for d in before.sales_orders} != {d.sales_order for d in self.sales_orders}:
			frappe.throw(_("Use Add New Orders to add Sales Orders after submit."))
		required = {d.name: (flt(d.required_qty), d.customer_breakdown) for d in before.items}
		if any(required.get(d.name) != (flt(d.required_qty), d.customer_breakdown) for d in self.items):
			frappe.throw(_("Required Qty comes from Sales Orders and cannot be edited."))

	def validate_billed_lines_unchanged(self):
		"""A supplier line already on a submitted Purchase Invoice cannot be changed or removed."""
		before = self.get_doc_before_save()
		if not before:
			return
		now = {d.name: d for d in self.supplier_lines}
		for old in before.supplier_lines:
			if not old.purchase_invoice:
				continue
			new = now.get(old.name)
			if not new or any(old.get(f) != new.get(f) for f in ("item_code", "supplier", "qty", "rate")):
				frappe.throw(
					_("Supplier line {0} / {1} is billed in {2}. Cancel the Purchase Invoice first.").format(
						old.item_code, old.supplier, frappe.get_desk_link("Purchase Invoice", old.purchase_invoice)
					)
				)

	def validate_supplier_lines(self):
		items = {d.item_code for d in self.items}
		seen = set()
		for line in self.supplier_lines:
			if line.item_code not in items:
				frappe.throw(
					_("Supplier line #{0}: Item {1} is not in this sheet.").format(line.idx, frappe.bold(line.item_code))
				)
			# One invoice row per item and supplier (it links to one Purchase Receipt row).
			key = (line.item_code, line.supplier)
			if key in seen:
				frappe.throw(
					_("Supplier line #{0}: {1} from {2} is already entered. Add the qty to that line.").format(
						line.idx, frappe.bold(line.item_code), frappe.bold(line.supplier)
					)
				)
			seen.add(key)

	def validate_duplicate_items(self):
		seen = set()
		for row in self.items:
			key = (row.item_code, row.uom)
			if key in seen:
				frappe.throw(
					_("Row #{0}: Item {1} ({2}) is already in the sheet.").format(
						row.idx, frappe.bold(row.item_code), row.uom
					)
				)
			seen.add(key)

	def validate_duplicate_sales_orders(self):
		orders = [d.sales_order for d in self.sales_orders]
		duplicates = {so for so in orders if orders.count(so) > 1}
		if duplicates:
			frappe.throw(_("Sales Order {0} is added more than once.").format(", ".join(duplicates)))

	# ---------- Totals & status ----------

	def calculate_totals(self):
		qty, amount = defaultdict(float), defaultdict(float)
		for line in self.supplier_lines:
			line.amount = flt(line.qty) * flt(line.rate)
			qty[line.item_code] += flt(line.qty)
			amount[line.item_code] += line.amount
		# Item row = sum of its supplier lines (average rate when bought from several suppliers).
		for row in self.items:
			row.ordered_qty = qty[row.item_code]
			row.amount = amount[row.item_code]
			row.rate = row.amount / row.ordered_qty if row.ordered_qty else 0
		self.total_required_qty = sum(flt(d.required_qty) for d in self.items)
		self.total_ordered_qty = sum(flt(d.ordered_qty) for d in self.items)
		self.total_received_qty = sum(flt(d.received_qty) for d in self.items)
		self.total_amount = sum(flt(d.amount) for d in self.items)

	def set_status(self, update=False):
		self.status = self.get_status()
		if update:
			self.db_set("status", self.status, update_modified=False)

	def get_status(self):
		if self.docstatus == 2:
			return "Cancelled"
		if self.docstatus == 0:
			return "Draft"
		lines = self.supplier_lines or []
		if lines and all(d.purchase_invoice for d in lines):
			return "Billed"
		rows = [d for d in self.items if flt(d.received_qty) > 0]
		if rows and all(d.purchase_receipt or not d.is_stock_item for d in rows):
			return "Received"
		return "Purchasing"
