import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

# These must match your Opportunity status names exactly [cite: 131]
OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def make_list_url(user_email, extra_filters=None):
    """
    Constructs the URL using separate parameters. 
    Using JSON arrays with operators like 'in' or 'like' forces them 
    into the Advanced Filters pop-up.
    """
    # 1. Status Filter: Using 'in' forces it into the Advanced UI
    status_json = json.dumps(["in", OPEN_STATUSES])
    
    # 2. Assigned To Filter: Targets the internal _assign field [cite: 126]
    assign_json = json.dumps(["like", f"%{user_email}%"])
    
    # Build the base URL
    url = (
        f"/app/opportunity/view/list?"
        f"status={urllib.parse.quote(status_json)}&"
        f"_assign={urllib.parse.quote(assign_json)}"
    )
    
    # 3. Add column-specific filters (e.g., deadline_date) [cite: 150, 155-156]
    if extra_filters:
        for field, op_val in extra_filters.items():
            encoded_val = urllib.parse.quote(json.dumps(op_val))
            url += f"&{field}={encoded_val}"
            
    return url

def execute(filters=None):
    # Defining columns as HTML to render links directly from Python [cite: 61-105]
    columns = [
        {"label": _("Assigned To"), "fieldname": "assigned_user", "fieldtype": "Link", "options": "User", "width": 220},
        {"label": _("Open"), "fieldname": "open_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Expired"), "fieldname": "expired_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Closing This Week"), "fieldname": "closing_week", "fieldtype": "HTML", "width": 150},
    ]

    # Data fetching logic [cite: 106-137]
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

        def get_html_link(count, extra=None):
            if count and count > 0:
                # Every link now includes Status and Assigned To by default
                url = make_list_url(user, extra)
                return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'
            return "0"

        data.append({
            "assigned_user": user,
            "open_count": get_html_link(row.open_count),
            "expired_count": get_html_link(row.expired_count, {"deadline_date": ["<", current_date]}),
            "closing_week": get_html_link(row.closing_week, {"deadline_date": ["between", [current_date, week_end]]}),
        })

    return columns, data