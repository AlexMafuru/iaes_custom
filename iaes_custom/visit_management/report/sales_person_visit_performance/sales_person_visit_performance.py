# Copyright (c) 2026, Sales Team Strategy and contributors
"""Sales Person Visit Performance.

The three metrics ranked first in the requirements checklist (B6.1) are
Completion Rate, Visits to Quotation, and Follow-ups Overdue - they are the
leftmost metric columns here so they read first.

Conversion is attributed when a Quotation or Sales Order is raised for the same
party within CONVERSION_WINDOW_DAYS after the actual visit date, or when the
document is linked directly on the visit.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, flt, add_days

CONVERSION_WINDOW_DAYS = 30


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = get_data(filters)
    return get_columns(), data, None, get_chart(data)


def get_columns():
    return [
        {"label": _("Sales Person"), "fieldname": "assigned_to", "fieldtype": "Link",
         "options": "Sales Person", "width": 170},
        {"label": _("Target"), "fieldname": "target_visits", "fieldtype": "Int",
         "width": 80},
        {"label": _("Planned"), "fieldname": "planned", "fieldtype": "Int", "width": 85},
        {"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int",
         "width": 95},
        {"label": _("Completion %"), "fieldname": "completion_rate",
         "fieldtype": "Percent", "width": 115},
        {"label": _("Visits to Quotation"), "fieldname": "to_quotation",
         "fieldtype": "Int", "width": 145},
        {"label": _("Follow-ups Overdue"), "fieldname": "followups_overdue",
         "fieldtype": "Int", "width": 150},
        {"label": _("vs Target %"), "fieldname": "target_achievement",
         "fieldtype": "Percent", "width": 105},
        {"label": _("On-Time %"), "fieldname": "on_time_rate", "fieldtype": "Percent",
         "width": 100},
        {"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Int", "width": 85},
        {"label": _("Avg Days to Close"), "fieldname": "avg_days_to_close",
         "fieldtype": "Float", "precision": 1, "width": 140},
        {"label": _("Successful"), "fieldname": "successful", "fieldtype": "Int",
         "width": 100},
        {"label": _("Partial"), "fieldname": "partial", "fieldtype": "Int", "width": 85},
        {"label": _("Unproductive"), "fieldname": "unproductive", "fieldtype": "Int",
         "width": 115},
        {"label": _("Follow-ups Created"), "fieldname": "followups_created",
         "fieldtype": "Int", "width": 145},
        {"label": _("Visits to Order"), "fieldname": "to_sales_order",
         "fieldtype": "Int", "width": 130},
    ]


def get_sales_persons(filters):
    if filters.get("sales_person"):
        return [filters.sales_person]
    return frappe.get_all(
        "Sales Person", filters={"enabled": 1, "is_group": 0}, pluck="name"
    ) or frappe.get_all("Sales Person", filters={"is_group": 0}, pluck="name")


def get_data(filters):
    from iaes_custom.visit_management.doctype.visit_target.visit_target import (
        get_weekly_target,
    )

    conditions = ["cv.visit_date BETWEEN %(from_date)s AND %(to_date)s"]
    if filters.get("territory"):
        conditions.append("cv.territory = %(territory)s")
    where = " AND ".join(conditions)

    visits = frappe.db.sql(
        f"""
        SELECT cv.name, cv.assigned_to, cv.status, cv.visit_date,
               cv.actual_visit_date, cv.original_planned_date, cv.visit_outcome,
               cv.party_type, cv.party, cv.follow_up_required, cv.follow_up_date,
               cv.follow_up_reference_type, cv.follow_up_reference
        FROM `tabCustomer Visit` cv
        WHERE {where}
        """,
        filters, as_dict=True,
    )

    weeks = get_week_span(filters)
    today = getdate(nowdate())
    buckets = {}

    for sp in get_sales_persons(filters):
        buckets[sp] = frappe._dict({
            "assigned_to": sp, "planned": 0, "completed": 0, "overdue": 0,
            "on_time": 0, "days_sum": 0, "successful": 0, "partial": 0,
            "unproductive": 0, "followups_created": 0, "followups_overdue": 0,
            "to_quotation": 0, "to_sales_order": 0,
            "target_visits": int(flt(get_weekly_target(sp, filters.to_date)) * weeks),
        })

    for v in visits:
        b = buckets.get(v.assigned_to)
        if b is None:
            continue
        if v.status == "Cancelled":
            continue

        b.planned += 1

        if v.status == "Open" and v.visit_date and getdate(v.visit_date) < today:
            b.overdue += 1

        if v.status == "Closed":
            b.completed += 1
            baseline = v.original_planned_date or v.visit_date
            if v.actual_visit_date and baseline:
                delta = (getdate(v.actual_visit_date) - getdate(baseline)).days
                b.days_sum += delta
                if delta <= 0:
                    b.on_time += 1

            outcome = v.visit_outcome or ""
            if outcome.startswith("Successful"):
                b.successful += 1
            elif outcome.startswith("Partially"):
                b.partial += 1
            else:
                b.unproductive += 1

            if is_converted(v, "Quotation"):
                b.to_quotation += 1
            if is_converted(v, "Sales Order"):
                b.to_sales_order += 1

        if v.follow_up_required:
            b.followups_created += 1
            if v.follow_up_date and getdate(v.follow_up_date) < today:
                if is_followup_open(v):
                    b.followups_overdue += 1

    rows = []
    for b in buckets.values():
        b.completion_rate = round(b.completed * 100.0 / b.planned, 1) if b.planned else 0.0
        b.on_time_rate = round(b.on_time * 100.0 / b.completed, 1) if b.completed else 0.0
        b.avg_days_to_close = round(b.days_sum / b.completed, 1) if b.completed else 0.0
        b.target_achievement = round(
            b.completed * 100.0 / b.target_visits, 1) if b.target_visits else 0.0
        rows.append(b)

    rows.sort(key=lambda r: (-r.completion_rate, -r.completed))
    return rows


def get_week_span(filters):
    days = (getdate(filters.to_date) - getdate(filters.from_date)).days + 1
    return max(days / 7.0, 0)


def is_converted(visit, doctype):
    """Linked directly on the visit, or raised for the same party within the
    conversion window after the visit took place."""
    if visit.follow_up_reference_type == doctype and visit.follow_up_reference:
        return True

    if frappe.db.exists("Visit Reference", {
        "parent": visit.name, "reference_type": doctype
    }):
        return True

    if visit.party_type != "Customer" or not visit.actual_visit_date:
        return False

    # Quotation stores the customer in party_name; Sales Order in customer.
    party_field = "party_name" if doctype == "Quotation" else "customer"
    window_end = add_days(getdate(visit.actual_visit_date), CONVERSION_WINDOW_DAYS)

    return bool(frappe.get_all(
        doctype,
        filters={
            party_field: visit.party,
            "docstatus": ["<", 2],
            "transaction_date": ["between", [visit.actual_visit_date, window_end]],
        },
        limit=1,
    ))


def is_followup_open(visit):
    if not visit.follow_up_reference:
        return True
    if visit.follow_up_reference_type == "ToDo":
        return frappe.db.get_value(
            "ToDo", visit.follow_up_reference, "status") == "Open"
    if visit.follow_up_reference_type == "Customer Visit":
        return frappe.db.get_value(
            "Customer Visit", visit.follow_up_reference, "status") in (
                "Open", "In Progress")
    return False


def get_chart(data):
    rows = [r for r in data if r.get("planned")]
    if not rows:
        return None
    return {
        "data": {
            "labels": [r.assigned_to for r in rows],
            "datasets": [
                {"name": _("Planned"), "values": [r.planned for r in rows]},
                {"name": _("Completed"), "values": [r.completed for r in rows]},
            ],
        },
        "type": "bar",
        "colors": ["#C9D6E4", "#1F3864"],
        "barOptions": {"stacked": False},
    }
