"""Patch v0_0_6: own the Technician Registrar role.

Creates (idempotently) the role that allows designated staff to
register new field technicians without full HR access:

- Role "Technician Registrar" (desk access)
- Employee: read / write / create
- Department, Designation, Employment Type, Branch: read only
- Assigns the role to musa@iaestz.com if that user exists

All of this already exists on the live site (created via System
Console); this patch records it in the app so it is version-
controlled and reproducible on any fresh install.
"""

import frappe

ROLE = "Technician Registrar"
ASSIGN_TO = ["musa@iaestz.com"]

PERMS = {
    "Employee": {"read": 1, "write": 1, "create": 1},
    "Department": {"read": 1},
    "Designation": {"read": 1},
    "Employment Type": {"read": 1},
    "Branch": {"read": 1},
}


def ensure_role():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc(
            {"doctype": "Role", "role_name": ROLE, "desk_access": 1}
        ).insert(ignore_permissions=True)


def ensure_perms():
    for dt, perms in PERMS.items():
        if frappe.db.exists("Custom DocPerm", {"parent": dt, "role": ROLE}):
            continue
        row = {
            "doctype": "Custom DocPerm",
            "parent": dt,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": ROLE,
            "permlevel": 0,
        }
        row.update(perms)
        frappe.get_doc(row).insert(ignore_permissions=True)


def ensure_assignments():
    for user in ASSIGN_TO:
        if not frappe.db.exists("User", user):
            continue
        doc = frappe.get_doc("User", user)
        if ROLE not in [r.role for r in doc.roles]:
            doc.append("roles", {"role": ROLE})
            doc.save(ignore_permissions=True)


def execute():
    ensure_role()
    ensure_perms()
    ensure_assignments()
