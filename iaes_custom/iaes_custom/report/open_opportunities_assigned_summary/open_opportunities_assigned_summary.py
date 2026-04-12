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
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("Expired"),
            "fieldname": "expired_count",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("Closing This Week"),
            "fieldname": "closing_week",
            "fieldtype": "Int",
            "width": 150,
        },
        {
            "label": _("Open URL"),
            "fieldname": "open_url",
            "fieldtype": "Data",
            "hidden": 1,
        },
        {
            "label": _("Expired URL"),
            "fieldname": "expired_url",
            "fieldtype": "Data",
            "hidden": 1,
        },
        {
            "label": _("Closing Week URL"),
            "fieldname": "closing_week_url",
            "fieldtype": "Data",
            "hidden": 1,
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
        assigned_user = row.assigned_user
        assign_pattern = f'%"{assigned_user}"%'

        open_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", assign_pattern],
        ]

        expired_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", assign_pattern],
            ["Opportunity", "deadline_date", "<", current_date],
        ]

        closing_week_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", assign_pattern],
            ["Opportunity", "deadline_date", ">=", current_date],
            ["Opportunity", "deadline_date", "<=", week_end],
        ]

        data.append(
            {
                "assigned_user": assigned_user,
                "open_count": row.open_count,
                "expired_count": row.expired_count,
                "closing_week": row.closing_week,
                "open_url": make_list_url(open_filters),
                "expired_url": make_list_url(expired_filters),
                "closing_week_url": make_list_url(closing_week_filters),
            }
        )

    return columns, data