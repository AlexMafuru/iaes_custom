import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

# These must match your Opportunity status names exactly
OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def execute(filters=None):
    # Defining columns as HTML to render links directly from Python [cite: 228-272]
    columns = [
        {"label": _("Assigned To"), "fieldname": "assigned_user", "fieldtype": "Link", "options": "User", "width": 220},
        {"label": _("Open"), "fieldname": "open_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Expired"), "fieldname": "expired_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Closing This Week"), "fieldname": "closing_week", "fieldtype": "HTML", "width": 150},
    ]

    # Standard SQL logic for counts [cite: 273-304]
    rows = frappe.db.sql("""
        SELECT
            u.name AS assigned_user,
            COUNT(DISTINCT o.name) AS open_count,
            COUNT(DISTINCT CASE 
                WHEN o.deadline_date IS NOT NULL AND o.deadline_date < CURDATE() 
                THEN o.name END) AS expired_count,
            COUNT(DISTINCT CASE 
                WHEN o.deadline_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY) 
                THEN o.name END) AS closing_week
        FROM `tabUser` u
        LEFT JOIN `tabOpportunity` o ON COALESCE(o._assign, '') LIKE CONCAT('%%', u.name, '%%')
        WHERE u.enabled = 1 AND u.user_type = 'System User'
            AND o.docstatus < 2 AND o.status IN ('Open', 'In preparation', 'In Preparation')
        GROUP BY u.name
        HAVING open_count > 0 OR expired_count > 0 OR closing_week > 0
        ORDER BY open_count DESC, assigned_user
    """, as_dict=True)

    data = []
    current_date = today()
    week_end = add_days(current_date, 7)

    for row in rows:
        user = row.assigned_user

        def get_link(count, extra_dict=None):
            if not count or count <= 0:
                return "0"

            # Create a dictionary of filters. 
            # This format is REQUIRED to force both into the "Filters" pop-over.
            filter_dict = {
                "status": ["in", OPEN_STATUSES],
                "_assign": ["like", f"%{user}%"]
            }
            
            if extra_dict:
                filter_dict.update(extra_dict)

            # URL Encode the JSON dictionary 
            encoded = urllib.parse.quote(json.dumps(filter_dict))
            url = f"/app/opportunity/view/list?filters={encoded}"
            
            return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'

        data.append({
            "assigned_user": user,
            "open_count": get_link(row.open_count),
            "expired_count": get_link(row.expired_count, {"deadline_date": ["<", current_date]}),
            "closing_week": get_link(row.closing_week, {"deadline_date": ["between", [current_date, week_end]]}),
        })

    return columns, data