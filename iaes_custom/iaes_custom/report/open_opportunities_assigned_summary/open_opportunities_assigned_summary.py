import json
import urllib.parse

import frappe
from frappe import _
from frappe.utils import today, add_days


OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]


def make_list_url(filters):
    encoded = urllib.parse.quote(json.dumps(filters))
    return f"/app/opportunity/view/list?filters={encoded}"


def make_link(label, url):
    return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{label}</a>'


def get_names_for_bucket(assigned_user, bucket, current_date, week_end):
    conditions = [
        "docstatus < 2",
        "status in %(statuses)s",
        "coalesce(_assign, '') like %(assign_like)s",
    ]

    values = {
        "statuses": tuple(OPEN_STATUSES),
        "assign_like": f'%"{assigned_user}"%',
        "current_date": current_date,
        "week_end": week_end,
    }

    if bucket == "expired":
        conditions.append("deadline_date is not null")
        conditions.append("deadline_date < %(current_date)s")
    elif bucket == "closing_week":
        conditions.append("deadline_date is not null")
        conditions.append("deadline_date >= %(current_date)s")
        conditions.append("deadline_date <= %(week_end)s")

    where_clause = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT name
        FROM `tabOpportunity`
        WHERE {where_clause}
        ORDER BY name
        """,
        values,
        as_dict=True,
    )

    return [r.name for r in rows]


def execute(filters=None):
    columns = [
        {
            "label": _("Assigned To"),
            "fieldname": "assigned_user",
            "fieldtype": "Link",
            "options": "User",
            "width": 220,
        },
        {
            "label": _("Open"),
            "fieldname": "open_count",
            "fieldtype": "HTML",
            "width": 100,
        },
        {
            "label": _("Expired"),
            "fieldname": "expired_count",
            "fieldtype": "HTML",
            "width": 100,
        },
        {
            "label": _("Closing This Week"),
            "fieldname": "closing_week",
            "fieldtype": "HTML",
            "width": 150,
        },
    ]

    rows = frappe.db.sql(
        """
        SELECT
            u.name AS assigned_user,
            COUNT(DISTINCT o.name) AS open_count,
            COUNT(
                DISTINCT CASE
                    WHEN o.deadline_date IS NOT NULL
                     AND o.deadline_date < CURDATE()
                    THEN o.name
                END
            ) AS expired_count,
            COUNT(
                DISTINCT CASE
                    WHEN o.deadline_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
                    THEN o.name
                END
            ) AS closing_week
        FROM `tabUser` u
        LEFT JOIN `tabOpportunity` o
            ON COALESCE(o._assign, '') LIKE CONCAT('%%', u.name, '%%')
        WHERE
            u.enabled = 1
            AND u.user_type = 'System User'
            AND o.docstatus < 2
            AND o.status IN ('Open', 'In preparation', 'In Preparation')
        GROUP BY u.name
        HAVING open_count > 0 OR expired_count > 0 OR closing_week > 0
        ORDER BY open_count DESC, assigned_user
        """,
        as_dict=True,
    )

    data = []
    current_date = today()
    week_end = add_days(current_date, 7)

    for row in rows:
        user = row.assigned_user

        open_names = get_names_for_bucket(user, "open", current_date, week_end)
        expired_names = get_names_for_bucket(user, "expired", current_date, week_end)
        week_names = get_names_for_bucket(user, "closing_week", current_date, week_end)

        def build_url(names):
            if not names:
                return None
            return make_list_url([
                ["Opportunity", "name", "in", names]
            ])

        open_url = build_url(open_names)
        expired_url = build_url(expired_names)
        week_url = build_url(week_names)

        data.append({
            "assigned_user": user,
            "open_count": make_link(row.open_count, open_url) if open_url else "0",
            "expired_count": make_link(row.expired_count, expired_url) if expired_url else "0",
            "closing_week": make_link(row.closing_week, week_url) if week_url else "0",
        })

    return columns, data