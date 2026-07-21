"""Patch v0_0_4: own the Expense Claim "Field Technician" customisations.

Ensures (idempotently):
1. Custom Field Expense Claim-custom_field_technician
   (Link -> Employee, dropdown filtered to Active Piecework employees).
2. The list-view Client Script that applies the same filter to the
   Field Technician standard-filter dropdown.

Both already exist on the live site (created manually); this patch
records them in the app so any fresh install gets them automatically.

NOTE: Task filters technicians by department (Field Operations), while
Expense Claim filters by employment type (Piecework). Today both
resolve to the same six people; unify the rule if they ever drift.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

LINK_FILTERS = json.dumps([
    ["Employee", "employment_type", "=", "Piecework"],
    ["Employee", "status", "=", "Active"],
])

CLIENT_SCRIPT = """/* Field Technician filter - Expense Claim list view (iaes_custom v0_0_4) */
frappe.listview_settings["Expense Claim"] = frappe.listview_settings["Expense Claim"] || {};
(function () {
    const s = frappe.listview_settings["Expense Claim"];

    const apply = (listview) => {
        const fld =
            listview.page &&
            listview.page.fields_dict &&
            listview.page.fields_dict.custom_field_technician;
        if (fld) {
            fld.get_query = () => ({
                filters: {
                    employment_type: "Piecework",
                    status: "Active",
                },
            });
        }
    };

    const prev_onload = s.onload;
    s.onload = function (lv) {
        if (prev_onload) prev_onload.call(this, lv);
        apply(lv);
    };

    const prev_refresh = s.refresh;
    s.refresh = function (lv) {
        if (prev_refresh) prev_refresh.call(this, lv);
        apply(lv);
    };
})();
"""


def ensure_custom_field():
    name = "Expense Claim-custom_field_technician"
    if frappe.db.exists("Custom Field", name):
        doc = frappe.get_doc("Custom Field", name)
        doc.link_filters = LINK_FILTERS
        doc.in_standard_filter = 1
        doc.save()
    else:
        create_custom_fields({
            "Expense Claim": [
                {
                    "fieldname": "custom_field_technician",
                    "label": "Field Technician",
                    "fieldtype": "Link",
                    "options": "Employee",
                    "insert_after": "employee_name",
                    "link_filters": LINK_FILTERS,
                    "in_standard_filter": 1,
                }
            ]
        })


def ensure_client_script():
    target = None
    for n in frappe.get_all(
        "Client Script",
        filters={"dt": "Expense Claim", "view": "List"},
        pluck="name",
    ):
        script = frappe.db.get_value("Client Script", n, "script") or ""
        if "custom_field_technician" in script:
            target = n
            break

    if target:
        doc = frappe.get_doc("Client Script", target)
    else:
        doc = frappe.new_doc("Client Script")
        doc.dt = "Expense Claim"
        doc.view = "List"

    doc.script = CLIENT_SCRIPT
    doc.enabled = 1
    doc.save()


def execute():
    ensure_custom_field()
    ensure_client_script()
    frappe.clear_cache(doctype="Expense Claim")
