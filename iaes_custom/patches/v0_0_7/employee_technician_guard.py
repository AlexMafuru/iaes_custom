"""Patch v0_0_7: own the Employee 'Field Technician setup' guard.

Adopts (or creates) the Client Script on Employee (Form view) that
blocks saving a field technician whose record is missing or has the
wrong Designation (Technician), Department (Field Operations - IAES)
or Employment Type (Piecework). Either marker - the Technician
designation or the Piecework employment type - triggers the check.
"""

import frappe

CLIENT_SCRIPT = """frappe.ui.form.on("Employee", {
    validate(frm) {
        const desig = (frm.doc.designation || "").trim().toLowerCase();
        const etype = (frm.doc.employment_type || "").trim().toLowerCase();

        if (desig !== "technician" && etype !== "piecework") return;

        const missing = [];
        if (desig !== "technician")
            missing.push("Designation - must be <b>Technician</b>");
        if (frm.doc.department !== "Field Operations - IAES")
            missing.push("Department - must be <b>Field Operations - IAES</b> (currently: " + (frm.doc.department || "empty") + ")");
        if (etype !== "piecework")
            missing.push("Employment Type - must be <b>Piecework</b>");

        if (missing.length) {
            frappe.msgprint({
                title: __("Field Technician setup incomplete"),
                indicator: "orange",
                message: __(
                    "This looks like a field technician, but:<br><br>{0}<br><br>" +
                    "Fix these or the technician will not appear in the " +
                    "Field Technician dropdowns on Task and Expense Claim.",
                    [missing.join("<br>")]
                ),
            });
            frappe.validated = false;
        }
    },
});
"""


def execute():
    target = None
    for n in frappe.get_all(
        "Client Script",
        filters={"dt": "Employee", "view": "Form"},
        pluck="name",
    ):
        script = frappe.db.get_value("Client Script", n, "script") or ""
        if "Field Technician setup incomplete" in script:
            target = n
            break

    if target:
        doc = frappe.get_doc("Client Script", target)
    else:
        doc = frappe.new_doc("Client Script")
        doc.dt = "Employee"
        doc.view = "Form"

    doc.script = CLIENT_SCRIPT
    doc.enabled = 1
    doc.save()
