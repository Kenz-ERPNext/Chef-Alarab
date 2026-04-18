frappe.query_reports["Sales Order Summary"] = {
    "filters": [

        {
            "fieldname": "from_date",
            "label": "From Date",
            "fieldtype": "Date",
            "default": frappe.datetime.month_start(),
            "reqd": 1
        },

        {
            "fieldname": "to_date",
            "label": "To Date",
            "fieldtype": "Date",
            "default": frappe.datetime.month_end(),
            "reqd": 1
        },

        {
            "fieldname": "customer",
            "label": "Customer",
            "fieldtype": "Link",
            "options": "Customer"
        },

        {
            "fieldname": "item_code",
            "label": "Product",
            "fieldtype": "Link",
            "options": "Item"
        },

        {
            "fieldname": "customer_group",
            "label": "Customer Group",
            "fieldtype": "Link",
            "options": "Customer Group"
        },

        {
            "fieldname": "warehouse",
            "label": "Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse"
        }

    ],

    formatter: function (value, row, column, data, default_formatter) {

        value = default_formatter(value, row, column, data);

        if (data && data.is_total_row) {
            value = `<b style="color:#1abc9c">${value}</b>`;
        }

        if (data && data.to_purchase > 0 && column.fieldname === "to_purchase") {
            value = `<b style="color:red">${value}</b>`;
        }

        return value;
    }
};