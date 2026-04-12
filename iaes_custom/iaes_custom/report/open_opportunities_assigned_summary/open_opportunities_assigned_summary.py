import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

# These statuses must match your database exactly [cite: 223]
OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def make_ui_url(user_email, extra_filters=None):
    """
    Constructs a URL using the list-of-lists format.
    This forces every field into the 'Advanced Filters' pop-over.
    """
    # 1. Define the mandatory filters
    filters = [
        ["Opportunity", "status", "in", OPEN_STATUSES],
        ["Opportunity", "_assign", "like", f"%{user_email}%"]
    ]
    
    # 2. Add column-specific filters (like deadline_date) if provided [cite: 318, 323-324]
    if extra_filters:
        for field, op_val in extra_filters.items():
            # op_val is expected to be [operator, value] e.g., ["<", "2026-04-12"]
            filters.append(["Opportunity", field, op_val[0], op_val[1]])
            
    # 3. Bundle everything into the 'filters' parameter [cite: 225-226]
    encoded = urllib.parse.quote(json.dumps(filters))
    return f"/app/opportunity/view/list?filters={encoded}"

def execute(filters=None):
    # Standard column definitions using HTML fieldtype [cite: 228-272]
    columns = [
        {"label": _("Assigned To"), "fieldname": "assigned_user", "fieldtype": "Link", "options": "User", "width": 220},
        {"label": _("Open"), "fieldname": "open_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Expired"), "fieldname": "expired_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Closing This Week"), "fieldname": "closing_week", "fieldtype": "HTML", "width": 150},
    ]

    # Standard SQL logic for summary counts [cite: 273-304]
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
                # Use the explicit list-of-lists URL format [cite: 175, 178, 181]
                url = make_ui_url(user, extra)
                return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'
            return "0"

        data.append({
            "assigned_user": user,
            "open_count": get_html_link(row.open_count),
            "expired_count": get_html_link(row.expired_count, {"deadline_date": ["<", current_date]}),
            "closing_week": get_html_link(row.closing_week, {"deadline_date": ["between", [current_date, week_end]]}),
        })

    return columns, data