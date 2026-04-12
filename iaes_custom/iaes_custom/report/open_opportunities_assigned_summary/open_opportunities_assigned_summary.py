import json
import time
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

OPEN_STATUSES = ["Open", "In preparation"]

def make_ui_url(user_email, extra_filters=None):
    status_json = urllib.parse.quote(json.dumps(["in", OPEN_STATUSES]))
    assign_json = urllib.parse.quote(json.dumps(["like", f"%{user_email}%"]))
    ts = int(time.time() * 1000)

    url = (
        f"/app/opportunity/view/list"
        f"?status={status_json}"
        f"&_assign={assign_json}"
        f"&_ts={ts}"
    )

    if extra_filters:
        for fieldname, condition in extra_filters.items():
            encoded = urllib.parse.quote(json.dumps(condition))
            url += f"&{fieldname}={encoded}"

    return url

def get_indicator_html(color, label):
    return (
        f'<span style="display:inline-block; width:10px; height:10px; '
        f'border-radius:50%; background:{color}; margin-right:8px; '
        f'vertical-align:middle;"></span>'
        f'<span style="vertical-align:middle;">{label}</span>'
    )

def get_risk_color(value, low_warning=1, high_warning=3):
    value = value or 0
    if value == 0:
        return "#28a745"   # green
    elif value <= high_warning:
        return "#fd7e14"   # orange
    return "#dc3545"       # red

def get_clickable_count(count, url=None, color="var(--blue-600)"):
    count = count or 0
    if url and count > 0:
        return (
            f'<a href="{url}" '
            f'style="font-weight:bold; color:{color};">'
            f'{count}</a>'
        )
    return f'<span style="font-weight:bold; color:{color};">{count}</span>'

def execute(filters=None):
    columns = [
        {
            "label": _("Assigned To"),
            "fieldname": "assigned_user",
            "fieldtype": "Data",
            "width": 240,
        },
        {
            "label": _("Health"),
            "fieldname": "health_indicator",
            "fieldtype": "HTML",
            "width": 130,
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
            "width": 110,
        },
        {
            "label": _("Closing in 7 Days"),
            "fieldname": "closing_week",
            "fieldtype": "HTML",
            "width": 160,
        },
    ]

    current_date = str(today())
    closing_end = str(add_days(today(), 6))

    rows = frappe.db.sql("""
        SELECT
            u.name AS assigned_user,
            COUNT(DISTINCT o.name) AS open_count,
            COUNT(DISTINCT CASE
                WHEN o.deadline_date IS NOT NULL
                 AND o.deadline_date < CURDATE()
                THEN o.name END) AS expired_count,
            COUNT(DISTINCT CASE
                WHEN o.deadline_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 6 DAY)
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
    total_open = 0
    total_expired = 0
    total_closing = 0

    for row in rows:
        user = row.assigned_user
        open_count = row.open_count or 0
        expired_count = row.expired_count or 0
        closing_count = row.closing_week or 0

        total_open += open_count
        total_expired += expired_count
        total_closing += closing_count

        open_url = make_ui_url(user)
        expired_url = make_ui_url(user, {
            "deadline_date": ["<", current_date]
        })
        closing_url = make_ui_url(user, {
            "deadline_date": ["between", [current_date, closing_end]]
        })

        # Overall health logic
        # Red if expired > 3
        # Orange if expired > 0 or closing in 7 days > 2
        # Green otherwise
        if expired_count > 3:
            health_html = get_indicator_html("#dc3545", "Critical")
        elif expired_count > 0 or closing_count > 2:
            health_html = get_indicator_html("#fd7e14", "Attention")
        else:
            health_html = get_indicator_html("#28a745", "Healthy")

        expired_color = get_risk_color(expired_count, high_warning=3)
        closing_color = get_risk_color(closing_count, high_warning=2)

        data.append({
            "assigned_user": user,
            "health_indicator": health_html,
            "open_count": get_clickable_count(open_count, open_url, "var(--blue-600)"),
            "expired_count": get_clickable_count(expired_count, expired_url, expired_color),
            "closing_week": get_clickable_count(closing_count, closing_url, closing_color),
        })

    # Totals row
    total_health = get_indicator_html("#1f6feb", "Summary")

    data.append({
        "assigned_user": "<b>TOTAL</b>",
        "health_indicator": total_health,
        "open_count": f"<b>{total_open}</b>",
        "expired_count": f'<b style="color:{get_risk_color(total_expired, high_warning=3)};">{total_expired}</b>',
        "closing_week": f'<b style="color:{get_risk_color(total_closing, high_warning=2)};">{total_closing}</b>',
    })

    return columns, data