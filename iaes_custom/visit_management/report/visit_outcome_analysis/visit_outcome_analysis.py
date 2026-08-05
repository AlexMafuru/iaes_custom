# Copyright (c) 2026, Sales Team Strategy and contributors
"""Visit Outcome Analysis - outcomes cross-tabulated against visit purpose.

Answers which kinds of visit are actually worth making.
"""

import frappe
from frappe import _

OUTCOMES = [
    "Successful - Objective Achieved",
    "Partially Successful",
    "Postponed by Customer",
    "Customer Unavailable",
    "Cancelled",
]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = get_data(filters)
    return get_columns(), data, None, get_chart(data)


def get_columns():
    columns = [
        {"label": _("Visit Purpose"), "fieldname": "visit_purpose",
         "fieldtype": "Data", "width": 250},
        {"label": _("Closed"), "fieldname": "total", "fieldtype": "Int", "width": 90},
    ]
    for o in OUTCOMES:
        columns.append({
            "label": _(o.split(" - ")[0]), "fieldname": frappe.scrub(o),
            "fieldtype": "Int", "width": 130,
        })
    columns.append({
        "label": _("Success %"), "fieldname": "success_rate",
        "fieldtype": "Percent", "width": 110,
    })
    return columns


def get_data(filters):
    conditions = [
        "cv.status = 'Closed'",
        "COALESCE(cv.actual_visit_date, cv.visit_date) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    if filters.get("sales_person"):
        conditions.append("cv.assigned_to = %(sales_person)s")
    if filters.get("territory"):
        conditions.append("cv.territory = %(territory)s")

    rows = frappe.db.sql(
        f"""
        SELECT cv.visit_purpose, cv.visit_outcome, COUNT(*) AS cnt
        FROM `tabCustomer Visit` cv
        WHERE {' AND '.join(conditions)}
        GROUP BY cv.visit_purpose, cv.visit_outcome
        """,
        filters, as_dict=True,
    )

    buckets = {}
    for r in rows:
        b = buckets.setdefault(
            r.visit_purpose,
            frappe._dict({"visit_purpose": r.visit_purpose, "total": 0},
                         **{frappe.scrub(o): 0 for o in OUTCOMES}),
        )
        key = frappe.scrub(r.visit_outcome or "")
        if key in b:
            b[key] += r.cnt
        b.total += r.cnt

    data = []
    for b in buckets.values():
        good = b[frappe.scrub(OUTCOMES[0])] + b[frappe.scrub(OUTCOMES[1])]
        b.success_rate = round(good * 100.0 / b.total, 1) if b.total else 0.0
        data.append(b)

    data.sort(key=lambda r: -r["total"])
    return data


def get_chart(data):
    if not data:
        return None
    return {
        "data": {
            "labels": [r.visit_purpose for r in data],
            "datasets": [{"name": _("Success %"),
                          "values": [r.success_rate for r in data]}],
        },
        "type": "bar",
        "colors": ["#1F3864"],
    }
