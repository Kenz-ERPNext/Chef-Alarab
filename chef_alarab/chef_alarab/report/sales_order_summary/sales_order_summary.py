import frappe
from collections import defaultdict

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


# -----------------------------------------
# Columns
# -----------------------------------------
def get_columns():
    return [
        {"label": "Product Code", "fieldname": "item_code", "width": 120},
        {"label": "Customer", "fieldname": "customer", "width": 160},
        {"label": "Product Name", "fieldname": "item_name", "width": 180},
        {"label": "UOM", "fieldname": "uom", "width": 80},
        {"label": "UOM Packing", "fieldname": "packing", "fieldtype": "Float", "width": 120},
        {"label": "Ordered Qty", "fieldname": "qty", "fieldtype": "Float", "width": 110},
        {"label": "Sum", "fieldname": "sum_qty", "fieldtype": "Float", "width": 110},
        {"label": "W.Qty", "fieldname": "w_qty", "fieldtype": "Float", "width": 110},
        {"label": "To Purchase Qty", "fieldname": "to_purchase", "fieldtype": "Float", "width": 150},
    ]


# -----------------------------------------
# Data
# -----------------------------------------
def get_data(filters):

    conditions = ""

    if filters.get("from_date"):
        conditions += " AND so.transaction_date >= %(from_date)s"

    if filters.get("to_date"):
        conditions += " AND so.transaction_date <= %(to_date)s"

    if filters.get("customer"):
        conditions += " AND so.customer = %(customer)s"

    if filters.get("item_code"):
        conditions += " AND soi.item_code = %(item_code)s"

    if filters.get("customer_group"):
        conditions += " AND so.customer_group = %(customer_group)s"

    so_items = frappe.db.sql(f"""
        SELECT 
            soi.item_code,
            soi.item_name,
            soi.uom,
            soi.qty,
            soi.conversion_factor,
            so.customer
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1 {conditions}
        ORDER BY soi.item_code, soi.item_name
    """, filters, as_dict=1)

    grouped = defaultdict(list)

    # ✅ Better grouping
    for row in so_items:
        key = (row.item_code, row.item_name)
        grouped[key].append(row)

    data = []

    for (item_code, item_name), items in grouped.items():

        total_sum = 0

        # -------------------------
        # Row calculation
        # -------------------------
        for d in items:

            packing = d.conversion_factor or 1

            if d.uom and d.uom.lower() == "kg":
                sum_qty = d.qty
            else:
                sum_qty = d.qty * packing

            total_sum += sum_qty

            data.append({
                "item_code": d.item_code,
                "customer": d.customer,
                "item_name": d.item_name,
                "uom": d.uom,
                "packing": packing,
                "qty": d.qty,
                "sum_qty": sum_qty,
                "w_qty": "",
                "to_purchase": "",
                "is_total_row": 0
            })

        # -------------------------
        # Stock calculation
        # -------------------------
        if filters.get("warehouse"):
            stock_qty = frappe.db.sql("""
                SELECT SUM(actual_qty)
                FROM `tabBin`
                WHERE item_code = %s AND warehouse = %s
            """, (item_code, filters.get("warehouse")))[0][0] or 0
        else:
            stock_qty = frappe.db.sql("""
                SELECT SUM(actual_qty)
                FROM `tabBin`
                WHERE item_code = %s
            """, item_code)[0][0] or 0

        # -------------------------
        # Purchase calculation
        # -------------------------
        to_purchase = max(0, total_sum - stock_qty)

        # -------------------------
        # Total row
        # -------------------------
        data.append({
            "item_code": "",
            "customer": "",
            "item_name": f"Total ({item_name})",
            "uom": "",
            "packing": "",
            "qty": "",
            "sum_qty": total_sum,
            "w_qty": stock_qty,
            "to_purchase": to_purchase,
            "is_total_row": 1
        })

    return data


	