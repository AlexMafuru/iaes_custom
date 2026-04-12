import json
import urllib.parse
import frappe
from frappe import _
from frappe.utils import today, add_days

OPEN_STATUSES = ["Open", "In preparation", "In Preparation"]

def make_advanced_filter_url(assigned_user, extra_filters=None):
    """
    Constructs a URL that specifically targets the 'Filters' popover
    with Status and Assigned To.
    """
    # 1. Define the Status filter (In Open/In preparation)
    status_filter = json.dumps(["in", OPEN_STATUSES])
    
    # 2. Define the Assigned To filter (Like username)
    # We use _assign because that is the field the List View sidebar/filters use
    assign_filter = json.dumps(["like", f"%{assigned_user}%"])
    
    # Start building the URL with the two mandatory filters
    url = f"/app/opportunity/view/list?status={urllib.parse.quote(status_filter)}&_assign={urllib.parse.quote(assign_filter)}"
    
    # 3. Add extra date filters for Expired or Closing Week if needed
    if extra_filters:
        for field, value in extra_filters.items():
            encoded_val = urllib.parse.quote(json.dumps(value))
            url += f"&{field}={encoded_val}"
            
    return url

def execute(filters=None):
    columns = [
        {"label": _("Assigned To"), "fieldname": "assigned_user", "fieldtype": "Link", "options": "User", "width": 220},
        {"label": _("Open"), "fieldname": "open_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Expired"), "fieldname": "expired_count", "fieldtype": "HTML", "width": 100},
        {"label": _("Closing This Week"), "fieldname": "closing_week", "fieldtype": "HTML", "width": 150},
    ]

    # Get the data summary
    rows = frappe.db.sql("""
        SELECT
            u.name AS assigned_user,
            COUNT(DISTINCT o.name) AS open_count,
            COUNT(DISTINCT CASE 
                WHEN o.deadline_date < CURDATE() THEN o.name 
            END) AS expired_count,
            COUNT(DISTINCT CASE 
                WHEN o.deadline_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN o.name 
            END) AS closing_week
        FROM `tabUser` u
        LEFT JOIN `tabOpportunity` o ON o._assign LIKE CONCAT('%%', u.name, '%%')
        WHERE u.enabled = 1 AND u.user_type = 'System User'
            AND o.docstatus < 2
            AND o.status IN ('Open', 'In preparation', 'In Preparation')
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
            if count > 0:
                url = make_advanced_filter_url(user, extra)
                return f'<a href="{url}" style="font-weight:bold; color:var(--blue-600);">{count}</a>'
            return "0"

        data.append({
            "assigned_user": user,
            "open_count": get_html_link(row.open_count),
            "expired_count": get_html_link(row.expired_count, {"deadline_date": ["<", curr_date]}),
            "closing_week": get_html_link(row.closing_week, {"deadline_date": ["between", [curr_date, wk_end]]}),
        })

    return columns, data