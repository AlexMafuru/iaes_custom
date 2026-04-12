import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def make_list_url(filters_list):
    """
    Encodes filters into a single JSON array. 
    This format forces the List View to show all filters in the 'Filters' pop-over.
    """
    encoded = urllib.parse.quote(json.dumps(filters_list))
    return f"/app/opportunity/view/list?filters={encoded}"

def execute(filters=None):
    columns = [
        {"label": _("Assigned To"), "fieldname": "assigned_user", "fieldtype": "Link", "options": "User", "width": 220},
        {"label": _("Open"), "fieldname": "open_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Expired"), "fieldname": "expired_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Closing This Week"), "fieldname": "closing_week", "fieldtype": "HTML", "width": 150},
    ]

    # Data fetching remains the same as your working version
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
        LEFT JOIN `tabOpportunity` o ON o._assign LIKE CONCAT('%%', u.name, '%%')
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
        
        # Define the basic filters that apply to all counts
        # We use the [DocType, Field, Operator, Value] format for internal filters
        base_filters = [
            ["Opportunity", "status", "in", OPEN_STATUSES],
            ["Opportunity", "_assign", "like", f"%{user}%"]
        ]

        def get_link(count, extra_filter=None):
            if not count or count <= 0:
                return "0"
            
            # Combine base filters with column-specific filters
            current_filters = list(base_filters)
            if extra_filter:
                current_filters.append(extra_filter)
                
            url = make_list_url(current_filters)
            return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'

        data.append({
            "assigned_user": user,
            "open_count": get_link(row.open_count),
            "expired_count": get_link(row.expired_count, ["Opportunity", "deadline_date", "<", current_date]),
            "closing_week": get_link(row.closing_week, ["Opportunity", "deadline_date", "between", [current_date, week_end]]),
        })

    return columns, data