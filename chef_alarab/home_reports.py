# Copyright (c) 2026, Chef Al Arab and contributors
# For license information, please see license.txt
"""Puts a "Reports" card with the Chef Al Arab reports at the bottom of the Home workspace.

Home belongs to ERPNext, so it is not shipped as a fixture (that would overwrite it). Instead this
runs after every migrate and adds the card only when it is missing, also after ERPNext resets Home.
Written straight to the database so that saving Home never exports into the ERPNext app.
"""

import json

import frappe

WORKSPACE = "Home"
CARD = "Reports"  # not "Custom Reports": Frappe adds a card of that name to every workspace itself
REPORTS = ["Product Profit", "Region Wise Purchase", "Daily Profit Summary"]


def add_reports_card():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return
	if frappe.db.exists("Workspace Link", {"parent": WORKSPACE, "type": "Card Break", "label": CARD}):
		return
	reports = [r for r in REPORTS if frappe.db.exists("Report", r)]
	if not reports:
		return

	idx = frappe.db.sql("SELECT MAX(idx) FROM `tabWorkspace Link` WHERE parent = %s", WORKSPACE)[0][0] or 0
	rows = [{"type": "Card Break", "label": CARD, "link_count": len(reports)}]
	rows += [
		{"type": "Link", "label": r, "link_type": "Report", "link_to": r, "is_query_report": 1} for r in reports
	]
	for i, row in enumerate(rows, 1):
		link = frappe.new_doc("Workspace Link")
		link.update(row)
		link.update({"parent": WORKSPACE, "parenttype": "Workspace", "parentfield": "links", "idx": idx + i})
		link.db_insert()

	content = json.loads(frappe.db.get_value("Workspace", WORKSPACE, "content") or "[]")
	if not any(b.get("type") == "card" and b["data"].get("card_name") == CARD for b in content):
		cards = [i for i, b in enumerate(content) if b.get("type") == "card"]
		block = {"id": frappe.generate_hash(length=10), "type": "card", "data": {"card_name": CARD, "col": 4}}
		content.insert(cards[-1] + 1 if cards else len(content), block)
		frappe.db.set_value("Workspace", WORKSPACE, "content", json.dumps(content), update_modified=False)
	frappe.clear_cache()
