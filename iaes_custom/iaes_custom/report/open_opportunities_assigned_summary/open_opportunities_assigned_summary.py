import frappe
from frappe import _
from datetime import timedelta


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
            "width": 140,
        },
    ]

    data = frappe.db.sql(
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
        HAVING open_count > 0 OR expired_count > 0
        ORDER BY open_count DESC, assigned_user
        """,
        as_dict=True,
    )

    return columns, data