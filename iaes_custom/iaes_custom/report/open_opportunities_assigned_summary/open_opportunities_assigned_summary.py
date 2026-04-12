import json
import time
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

OPEN_STATUSES = ["Open", "In preparation"]

def make_ui_url(user_email, extra_filters=None):
    route_filters = [
        ["Opportunity", "_assign", "like", f"%{user_email}%"],
        ["Opportunity", "status", "in", OPEN_STATUSES],
    ]

    if extra_filters:
        route_filters.extend(extra_filters)

    filters_json = urllib.parse.quote(json.dumps(route_filters))
    assign_hint = urllib.parse.quote(json.dumps(["like", f"%{user_email}%"]))
    ts = int(time.time() * 1000)

    return (
        f"/app/opportunity/view/list"
        f"?filters={filters_json}"
        f"&_assign={assign_hint}"
        f"&_ts={ts}"
    )

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

    rows = frappe.db.sql("""
        SELECT
            u.name AS assigned_user,
            COUNT(DISTINCT o.name) AS open_count,
            COUNT(DISTINCT CASE
                WHEN o.deadline_date IS NOT NULL
                 AND o.deadline_date < CURDATE()
                THEN o.name END) AS expired_count,
            COUNT(DISTINCT CASE
                WHEN o.deadline_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
                THEN o.name END) AS closing_week
        FROM `tabUser` u
        LEFT JOIN `tabOpportunity` o
            ON COALESCE(o._assign, '') LIKE CONCAT('%%', u.name, '%%')
        WHERE
            u.enabled = 1
            AND u.user_type = 'System User'
            AND o.docstatus < 2
            AND o.status IN ('Open', 'In preparation')
        GROUP BY u.name
        HAVING open_count > 0 OR expired_count > 0 OR closing_week > 0
        ORDER BY open_count DESC, assigned_user
    """, as_dict=True)

    data = []
    current_date = today()
    week_end = add_days(current_date, 7)

    for row in rows:
        user = row.assigned_user

        def get_html_link(count, extra_filters=None):
            if count and count > 0:
                url = make_ui_url(user, extra_filters)
                return (
                    f'<a href="{url}" '
                    f'style="font-weight:bold; color:var(--blue-600);">'
                    f'{count}</a>'
                )
            return "0"

        data.append({
            "assigned_user": user,
            "open_count": get_html_link(row.open_count),
            "expired_count": get_html_link(
                row.expired_count,
                [
                    ["Opportunity", "deadline_date", "<", current_date]
                ]
            ),
            "closing_week": get_html_link(
                row.closing_week,
                [
                    ["Opportunity", "deadline_date", "between", [current_date, week_end]]
                ]
            ),
        })

    return columns, data