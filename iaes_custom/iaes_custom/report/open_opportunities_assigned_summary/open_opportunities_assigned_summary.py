import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

# Ensure these statuses match your Opportunity doctype exactly
OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def make_standard_url(user_email, extra_filters=None):
    """
    Standardizes the URL to use separate parameters for each field.
    This format is confirmed to populate 'Filters 2' and 'Filters 3' in the UI.
    """
    # 1. Build the base filters as JSON lists to trigger 'Advanced' mode in UI
    status_json = json.dumps(["in", OPEN_STATUSES])
    assign_json = json.dumps(["like", f"%{user_email}%"])
    
    # 2. Construct the URL with individual parameters
    url = (
        f"/app/opportunity/view/list?"
        f"status={urllib.parse.quote(status_json)}&"
        f"_assign={urllib.parse.quote(assign_json)}"
    )
    
    # 3. Append additional date filters if provided (for Expired/Closing columns)
    if extra_filters:
        for field, op_val in extra_filters.items():
            encoded_val = urllib.parse.quote(json.dumps(op_val))
            url += f"&{field}={encoded_val}"
            
    return url

def execute(filters=None):
    columns = [
        {"label": _("Assigned To"), "fieldname": "assigned_user", "fieldtype": "Link", "options": "User", "width": 220},
        {"label": _("Open"), "fieldname": "open_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Expired"), "fieldname": "expired_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Closing This Week"), "fieldname": "closing_week", "fieldtype": "HTML", "width": 150},
    ]

    # Data fetching logic using your validated SQL [cite: 106-137]
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
    curr_date = today()
    wk_end = add_days(curr_date, 7)

    for row in rows:
        user = row.assigned_user

        def get_html_link(count, extra=None):
            if count and count > 0:
                # Every link now uses the separate parameter format
                url = make_standard_url(user, extra)
                return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'
            return "0"

        data.append({
            "assigned_user": user,
            "open_count": get_html_link(row.open_count),
            "expired_count": get_html_link(row.expired_count, {"deadline_date": ["<", curr_date]}),
            "closing_week": get_html_link(row.closing_week, {"deadline_date": ["between", [curr_date, wk_end]]}),
        })

    return columns, data