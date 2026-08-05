# Copyright (c) 2026, Sales Team Strategy and contributors
"""Open / Overdue / In Progress / Closed counts per sales person.

Answers the "open visits, closed visits, pending visits" requirement directly.
Overdue is derived from visit_date, never stored.
"""

import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Sales Person"), "fieldname": "assigned_to", "fieldtype": "Link",
         "options": "Sales Person", "width": 200},
        {"label": _("Open"), "fieldname": "open_visits", "fieldtype": "Int", "width": 90},
        {"label": _("Overdue"), "fieldname": "overdue_visits", "fieldtype": "Int",
         "width": 100},
        {"label": _("In Progress"), "fieldname": "in_progress", "fieldtype": "Int",
         "width": 110},
        {"label": _("Closed"), "fieldname": "closed_visits", "fieldtype": "Int",
         "width": 90},
        {"label": _("Cancelled"), "fieldname": "cancelled_visits", "fieldtype": "Int",
         "width": 100},
        {"label": _("Total"), "fieldname": "total_visits", "fieldtype": "Int",
         "width": 90},
        {"label": _("% Closed"), "fieldname": "percent_closed", "fieldtype": "Percent",
         "width": 100},
    ]


def get_data(filters):
    conditions = ["cv.visit_date BETWEEN %(from_date)s AND %(to_date)s"]
    if filters.get("sales_person"):
        conditions.append("cv.assigned_to = %(sales_person)s")
    if filters.get("territory"):
        conditions.append("cv.territory = %(territory)s")
    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            cv.assigned_to,
            SUM(CASE WHEN cv.status = 'Open'
                     AND cv.visit_date >= CURDATE() THEN 1 ELSE 0 END) AS open_visits,
            SUM(CASE WHEN cv.status = 'Open'
                     AND cv.visit_date <  CURDATE() THEN 1 ELSE 0 END) AS overdue_visits,
            SUM(CASE WHEN cv.status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN cv.status = 'Closed' THEN 1 ELSE 0 END) AS closed_visits,
            SUM(CASE WHEN cv.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_visits,
            COUNT(*) AS total_visits
        FROM `tabCustomer Visit` cv
        WHERE {where}
        GROUP BY cv.assigned_to
        ORDER BY total_visits DESC
        """,
        filters, as_dict=True,
    )

    for r in rows:
        actionable = (r.total_visits or 0) - (r.cancelled_visits or 0)
        r["percent_closed"] = round(
            (r.closed_visits or 0) * 100.0 / actionable, 1) if actionable else 0.0

    if rows:
        total = frappe._dict({"assigned_to": _("Total")})
        for key in ("open_visits", "overdue_visits", "in_progress",
                    "closed_visits", "cancelled_visits", "total_visits"):
            total[key] = sum(r.get(key) or 0 for r in rows)
        actionable = total.total_visits - total.cancelled_visits
        total["percent_closed"] = round(
            total.closed_visits * 100.0 / actionable, 1) if actionable else 0.0
        rows.append(total)

    return rows
