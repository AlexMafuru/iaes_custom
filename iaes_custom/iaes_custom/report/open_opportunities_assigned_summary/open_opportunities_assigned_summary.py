import json
import urllib.parse

import frappe
from frappe import _
from frappe.utils import today, add_days

OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]


def make_list_url(filters):
    encoded = urllib.parse.quote(json.dumps(filters))
    return f"/app/opportunity/view/list?filters={encoded}"


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
        assign_pattern = f'%"{user}"%'

        open_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", assign_pattern],
        ]

        expired_filters = open_filters + [
            ["Opportunity", "deadline_date", "<", current_date]
        ]

        week_filters = open_filters + [
            ["Opportunity", "deadline_date", ">=", current_date],
            ["Opportunity", "deadline_date", "<=", week_end],
        ]

        def get_link(count, filters):
            if count and count > 0:
                url = make_list_url(filters)
                return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'
            return "0"

        data.append({
            "assigned_user": user,
            "open_count": get_link(row.open_count, open_filters),
            "expired_count": get_link(row.expired_count, expired_filters),
            "closing_week": get_link(row.closing_week, week_filters),
        })

    return columns, data