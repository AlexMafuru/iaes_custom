import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

# Constant for open statuses [cite: 223]
OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def make_list_url(filters_dict):
    """
    Constructs the URL using a dictionary for the 'filters' parameter.
    This format forces the UI to populate the Advanced Filters popover.
    """
    encoded = urllib.parse.quote(json.dumps(filters_dict))
    return f"/app/opportunity/view/list?filters={encoded}"

def execute(filters=None):
    # Column definitions [cite: 228-253]
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
        
        # We use a dictionary mapping field names to their filter arrays.
        # This format is essential for the UI to recognize 'Filters 2' .
        base_filters = {
            "status": ["in", OPEN_STATUSES],
            "_assign": ["like", f"%{user}%"]
        }

        def get_link(count, extra_filters=None):
            if not count or count <= 0:
                return "0"
            
            # Combine base filters with column-specific filters
            final_filters = base_filters.copy()
            if extra_filters:
                final_filters.update(extra_filters)
                
            url = make_list_url(final_filters)
            return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'

        data.append({
            "assigned_user": user,
            "open_count": get_link(row.open_count),
            "expired_count": get_link(row.expired_count, {"deadline_date": ["<", current_date]}),
            "closing_week": get_link(row.closing_week, {"deadline_date": ["between", [current_date, week_end]]})
        })

    return columns, data