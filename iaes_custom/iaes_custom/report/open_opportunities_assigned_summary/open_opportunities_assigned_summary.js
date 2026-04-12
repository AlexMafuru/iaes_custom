frappe.query_reports["Open Opportunities Assigned Summary"] = {
    "filters": [
        {
            "fieldname": "assigned_to",
            "label": __("User"),
            "fieldtype": "Link",
            "options": "User"
        }
    ]
};