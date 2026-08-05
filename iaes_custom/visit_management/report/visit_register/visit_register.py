# Copyright (c) 2026, Sales Team Strategy and contributors
"""Visit Register - every visit, filterable. The general-purpose lookup."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Visit"), "fieldname": "name", "fieldtype": "Link",
         "options": "Customer Visit", "width": 130},
        {"label": _("Status"), "fieldname": "display_status", "fieldtype": "Data",
         "width": 100},
        {"label": _("Visit Date"), "fieldname": "visit_date", "fieldtype": "Date",
         "width": 100},
        {"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
         "width": 90},
        {"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
         "options": "party_type", "width": 160},
        {"label": _("Name"), "fieldname": "party_name", "fieldtype": "Data",
         "width": 180},
        {"label": _("Assigned To"), "fieldname": "assigned_to", "fieldtype": "Link",
         "options": "Sales Person", "width": 140},
        {"label": _("Purpose"), "fieldname": "visit_purpose", "fieldtype": "Data",
         "width": 180},
        {"label": _("Outcome"), "fieldname": "visit_outcome", "fieldtype": "Data",
         "width": 180},
        {"label": _("Next Step"), "fieldname": "next_step", "fieldtype": "Data",
         "width": 160},
        {"label": _("Actual Date"), "fieldname": "actual_visit_date",
         "fieldtype": "Date", "width": 100},
        {"label": _("Days Late"), "fieldname": "days_late", "fieldtype": "Int",
         "width": 90},
        {"label": _("Follow-up"), "fieldname": "follow_up_date", "fieldtype": "Date",
         "width": 100},
        {"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link",
         "options": "Territory", "width": 120},
    ]


def get_conditions(filters):
    conditions = ["cv.visit_date BETWEEN %(from_date)s AND %(to_date)s"]
    if filters.get("sales_person"):
        conditions.append("cv.assigned_to = %(sales_person)s")
    if filters.get("territory"):
        conditions.append("cv.territory = %(territory)s")
    if filters.get("party_type"):
        conditions.append("cv.party_type = %(party_type)s")
    if filters.get("status"):
        conditions.append("cv.status = %(status)s")
    if filters.get("visit_purpose"):
        conditions.append("cv.visit_purpose = %(visit_purpose)s")
    return " AND ".join(conditions)


def get_data(filters):
    rows = frappe.db.sql(
        f"""
        SELECT cv.name, cv.status, cv.visit_date, cv.party_type, cv.party,
               cv.party_name, cv.assigned_to, cv.visit_purpose, cv.visit_outcome,
               cv.next_step, cv.actual_visit_date, cv.follow_up_date,
               cv.territory, cv.original_planned_date, cv.reschedule_count
        FROM `tabCustomer Visit` cv
        WHERE {get_conditions(filters)}
        ORDER BY cv.visit_date DESC, cv.name DESC
        """,
        filters, as_dict=True,
    )

    today = getdate(nowdate())
    only_overdue = filters.get("only_overdue")
    data = []

    for r in rows:
        # "Overdue" is derived here, exactly as in the list view - it is never
        # stored as a status value. See design note A1.
        if r.status == "Open" and r.visit_date and getdate(r.visit_date) < today:
            r["display_status"] = _("Overdue")
        else:
            r["display_status"] = _(r.status)

        baseline = r.original_planned_date or r.visit_date
        if r.actual_visit_date and baseline:
            r["days_late"] = (getdate(r.actual_visit_date) - getdate(baseline)).days
        elif r.status == "Open" and r.visit_date and getdate(r.visit_date) < today:
            r["days_late"] = (today - getdate(r.visit_date)).days
        else:
            r["days_late"] = 0

        if only_overdue and r["display_status"] != _("Overdue"):
            continue
        data.append(r)

    return data
