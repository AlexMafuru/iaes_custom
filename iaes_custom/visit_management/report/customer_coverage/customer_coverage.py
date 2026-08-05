# Copyright (c) 2026, Sales Team Strategy and contributors
"""Customer Coverage - who has not been visited, and for how long.

Sorted by days since last visit, descending. The neglected threshold comes from
Visit Management Settings (180 days per B2.7).
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
         "options": "Customer", "width": 220},
        {"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link",
         "options": "Territory", "width": 130},
        {"label": _("Customer Group"), "fieldname": "customer_group",
         "fieldtype": "Link", "options": "Customer Group", "width": 150},
        {"label": _("Last Visit"), "fieldname": "last_visit_date",
         "fieldtype": "Date", "width": 110},
        {"label": _("Days Since"), "fieldname": "days_since", "fieldtype": "Int",
         "width": 100},
        {"label": _("Coverage"), "fieldname": "coverage_status", "fieldtype": "Data",
         "width": 130},
        {"label": _("Last Visited By"), "fieldname": "last_visited_by",
         "fieldtype": "Link", "options": "Sales Person", "width": 150},
        {"label": _("Last Outcome"), "fieldname": "last_outcome", "fieldtype": "Data",
         "width": 180},
        {"label": _("Total Visits"), "fieldname": "total_visits", "fieldtype": "Int",
         "width": 110},
        {"label": _("Open Visits"), "fieldname": "open_visits", "fieldtype": "Int",
         "width": 110},
    ]


def get_data(filters):
    threshold = frappe.db.get_single_value(
        "Visit Management Settings", "neglected_customer_days") or 180

    conditions = ["c.disabled = 0"]
    values = {}
    if filters.get("territory"):
        conditions.append("c.territory = %(territory)s")
        values["territory"] = filters.territory
    if filters.get("customer_group"):
        conditions.append("c.customer_group = %(customer_group)s")
        values["customer_group"] = filters.customer_group

    customers = frappe.db.sql(
        f"""
        SELECT c.name AS customer, c.territory, c.customer_group
        FROM `tabCustomer` c
        WHERE {' AND '.join(conditions)}
        """,
        values, as_dict=True,
    )

    stats = frappe.db.sql(
        """
        SELECT cv.party AS customer,
               MAX(CASE WHEN cv.status = 'Closed'
                   THEN COALESCE(cv.actual_visit_date, cv.visit_date) END) AS last_visit_date,
               COUNT(*) AS total_visits,
               SUM(CASE WHEN cv.status IN ('Open', 'In Progress') THEN 1 ELSE 0 END)
                   AS open_visits
        FROM `tabCustomer Visit` cv
        WHERE cv.party_type = 'Customer'
        GROUP BY cv.party
        """,
        as_dict=True,
    )
    stat_map = {s.customer: s for s in stats}

    today = getdate(nowdate())
    data = []

    for c in customers:
        s = stat_map.get(c.customer)
        c["total_visits"] = s.total_visits if s else 0
        c["open_visits"] = s.open_visits if s else 0
        c["last_visit_date"] = s.last_visit_date if s else None

        if c["last_visit_date"]:
            c["days_since"] = (today - getdate(c["last_visit_date"])).days
            last = frappe.db.get_value(
                "Customer Visit",
                {"party_type": "Customer", "party": c.customer, "status": "Closed"},
                ["assigned_to", "visit_outcome"],
                order_by="COALESCE(actual_visit_date, visit_date) desc",
                as_dict=True,
            )
            if last:
                c["last_visited_by"] = last.assigned_to
                c["last_outcome"] = last.visit_outcome
        else:
            c["days_since"] = 9999
            c["last_visited_by"] = None
            c["last_outcome"] = None

        if not c["last_visit_date"]:
            c["coverage_status"] = _("Never Visited")
        elif c["days_since"] > threshold:
            c["coverage_status"] = _("Neglected")
        elif c["days_since"] > threshold / 2:
            c["coverage_status"] = _("Due Soon")
        else:
            c["coverage_status"] = _("Covered")

        if filters.get("only_neglected") and c["coverage_status"] == _("Covered"):
            continue
        data.append(c)

    data.sort(key=lambda r: -r["days_since"])
    return data
