"""Patch v0_0_5: own the Task list-view Field Technician filter script.

Adopts (or creates) the Client Script that restricts the Field
Technician standard-filter dropdown on the Task list view to active
employees of Field Operations - IAES, matching the link_filters on
Task-custom_field_technician (created in v0_0_3).
"""

import frappe

CLIENT_SCRIPT = """/* Field Technician filter - Task list view (iaes_custom v0_0_5) */
frappe.listview_settings["Task"] = frappe.listview_settings["Task"] || {};
(function () {
    const s = frappe.listview_settings["Task"];

    const apply = (listview) => {
        const fld =
            listview.page &&
            listview.page.fields_dict &&
            listview.page.fields_dict.custom_field_technician;
        if (fld) {
            fld.get_query = () => ({
                filters: {
                    department: "Field Operations - IAES",
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


def execute():
    target = None
    for n in frappe.get_all(
        "Client Script",
        filters={"dt": "Task", "view": "List"},
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
        doc.dt = "Task"
        doc.view = "List"

    doc.script = CLIENT_SCRIPT
    doc.enabled = 1
    doc.save()
    frappe.clear_cache(doctype="Task")
