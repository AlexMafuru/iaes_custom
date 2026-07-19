"""Patch: add "Field Technician" field to Task (ERPNext v15).

Registered in patches.txt as:
    iaes_custom.patches.v0_0_3.add_field_technician

Idempotent: create_custom_fields() syncs existing fields without
duplicating, so it is safe even though the fields were already
created on the live site via System Console.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_link_filters():
    """Resolve the real Department name (e.g. 'Field Operations - IAES')."""
    dept = frappe.db.get_value(
        "Department", {"department_name": "Field Operations"}, "name"
    )
    if not dept:
        return None  # field still gets created, just unfiltered
    return json.dumps([
        ["Employee", "department", "=", dept],
        ["Employee", "status", "=", "Active"],
    ])


def execute():
    create_custom_fields({
        "Task": [
            {
                "fieldname": "custom_field_technician",
                "label": "Field Technician",
                "fieldtype": "Link",
                "options": "Employee",
                "insert_after": "type",
                "link_filters": get_link_filters(),
                "in_standard_filter": 1,
            },
            {
                "fieldname": "custom_field_technician_name",
                "label": "Technician Name",
                "fieldtype": "Data",
                "insert_after": "custom_field_technician",
                "fetch_from": "custom_field_technician.employee_name",
                "read_only": 1,
            },
        ]
    })
    frappe.clear_cache(doctype="Task")
