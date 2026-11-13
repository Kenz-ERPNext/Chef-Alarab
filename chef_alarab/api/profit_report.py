# Copyright (c) 2026, Chef Al Arab and contributors
"""Daily Profit as a picture for the phone: the same numbers as the app and the desk report, on a page with the company letterhead."""

import frappe
from frappe import _
from frappe.utils import add_to_date, escape_html, formatdate

from chef_alarab.api.accounts import get_profit, pdf_to_png
from chef_alarab.chef_alarab.doctype.daily_purchase_sheet.daily_purchase_sheet import (
	ACCOUNTS_ROLES,
	require_role,
)

PAGE_CSS = """
body { font-family: sans-serif; font-size: 12px; color: #111; }
h2 { margin: 6px 0 2px; font-size: 18px; text-align: center; color: #c0392b; }
.period { text-align: center; margin-bottom: 10px; color: #333; }
table.pr { width: 100%; border-collapse: collapse; }
table.pr th, table.pr td { border: 1px solid #000; padding: 5px 7px; }
table.pr th { background: #eee; text-align: left; }
.num { text-align: right; white-space: nowrap; }
.total td { font-weight: bold; background: #f4f4f4; }
.loss { color: #c0392b; }
/* letterhead and footer images fit the page width, like in the other print formats */
.lh img, .lh table { width: 100% !important; max-width: 100% !important; height: auto !important; }
"""


def money(n):
	return f"{n:,.2f}"


def letter_head_parts():
	name = frappe.db.get_value("Letter Head", {"is_default": 1, "disabled": 0})
	if not name:
		return "", ""
	header, footer = frappe.db.get_value("Letter Head", name, ["content", "footer"])
	return header or "", footer or ""


def report_html(from_date, to_date):
	rows = get_profit(from_date, to_date)["rows"]
	header, footer = letter_head_parts()
	body = []
	for r in rows:
		total = bool(r.get("is_total"))
		label = _("Total") if total else formatdate(r["date"])
		klass = "total" if total else ""
		loss = " loss" if r["profit"] < 0 else ""
		body.append(
			f'<tr class="{klass}"><td>{escape_html(label)}</td><td class="num">{money(r["purchase"])}</td>'
			f'<td class="num">{money(r["system_sales"])}</td><td class="num{loss}">{money(r["profit"])}</td>'
			f'<td class="num{loss}">{r["profit_pct"]:.1f}%</td></tr>'
		)
	if not rows:
		body.append(f'<tr><td colspan="5">{escape_html(_("No purchases or sales in this period."))}</td></tr>')
	company = escape_html(frappe.defaults.get_user_default("Company") or "")
	return (
		f'<!doctype html><html><head><meta charset="utf-8"><style>{PAGE_CSS}</style></head><body>'
		f'<div class="lh">{header}</div>' f"<h2>{escape_html(_('Daily Profit'))}</h2>"
		f'<div class="period">{company}<br>{formatdate(from_date)} – {formatdate(to_date)} · {escape_html(_("amounts before VAT"))}</div>'
		f'<table class="pr"><thead><tr><th>{escape_html(_("Date"))}</th><th class="num">{escape_html(_("Total Purchase"))}</th>'
		f'<th class="num">{escape_html(_("System Sales"))}</th><th class="num">{escape_html(_("Profit"))}</th>'
		f'<th class="num">{escape_html(_("Profit %"))}</th></tr></thead><tbody>{"".join(body)}</tbody></table>'
		f'<div class="lh" style="margin-top:14px">{footer}</div></body></html>'
	)


@frappe.whitelist()
def profit_report_image(from_date: str, to_date: str):
	"""The Daily Profit rows of a period as a PNG for the phone's gallery."""
	require_role(ACCOUNTS_ROLES, _("see profit"))
	from frappe.utils.pdf import get_pdf

	pdf = get_pdf(
		report_html(from_date, to_date),
		{"margin-top": "8mm", "margin-bottom": "8mm", "margin-left": "8mm", "margin-right": "8mm"},
	)
	frappe.local.response.filename = f"Daily-Profit-{from_date}.png"
	frappe.local.response.filecontent = pdf_to_png(pdf)
	frappe.local.response.type = "download"
