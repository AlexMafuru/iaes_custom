import json

import frappe
from frappe import _
from frappe.utils import nowdate

OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]


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
            "label": _("Open Filters"),
            "fieldname": "open_filters",
            "fieldtype": "Data",
            "hidden": 1,
        },
        {
            "label": _("Expired Filters"),
            "fieldname": "expired_filters",
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
                    WHEN o.expected_closing IS NOT NULL
                     AND DATE(o.expected_closing) < CURDATE()
                    THEN o.name
                END
            ) AS expired_count
        FROM `tabUser` u
        INNER JOIN `tabOpportunity` o
            ON COALESCE(o._assign, '') LIKE CONCAT('%%', u.name, '%%')
        WHERE
            u.enabled = 1
            AND u.user_type = 'System User'
            AND o.docstatus < 2
            AND o.status IN ('Open', 'In preparation', 'In Preparation')
        GROUP BY u.name
        HAVING open_count > 0 OR expired_count > 0
        ORDER BY open_count DESC, assigned_user
        """,
        as_dict=True,
    )

    data = []
    for row in rows:
        assigned_user = row.assigned_user

        open_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", f"%{assigned_user}%"],
        ]

        expired_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", f"%{assigned_user}%"],
            ["Opportunity", "expected_closing", "<", nowdate()],
        ]

        data.append(
            {
                "assigned_user": assigned_user,
                "open_count": row.open_count,
                "expired_count": row.expired_count,
                "open_filters": json.dumps(open_filters),
                "expired_filters": json.dumps(expired_filters),
            }
        )

    return columns, data
