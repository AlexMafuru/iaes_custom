import frappe
from frappe import _
from frappe.utils import flt, cstr, nowdate, date_diff


def execute(filters=None):
    if not filters:
        filters = {}
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    summary = get_report_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"label": _("Project ID"),                  "fieldname": "project",             "fieldtype": "Link",     "options": "Project",  "width": 130},
        {"label": _("Project Name"),                 "fieldname": "project_name",        "fieldtype": "Data",                            "width": 220},
        {"label": _("Customer"),                     "fieldname": "customer",            "fieldtype": "Link",     "options": "Customer", "width": 160},
        {"label": _("Status"),                       "fieldname": "status",              "fieldtype": "Data",                            "width": 90},
        {"label": _("% Complete"),                   "fieldname": "percent_complete",    "fieldtype": "Percent",                         "width": 90},
        {"label": _("SO Value / Project Value"),     "fieldname": "so_value",            "fieldtype": "Currency", "options": "currency", "width": 180},
        {"label": _("SO Count"),                     "fieldname": "so_count",            "fieldtype": "Int",                             "width": 80},
        {"label": _("SINV Billed (Base CCY)"),       "fieldname": "sinv_value",          "fieldtype": "Currency", "options": "currency", "width": 170},
        {"label": _("SINV Collected (Base CCY)"),    "fieldname": "sinv_paid",           "fieldtype": "Currency", "options": "currency", "width": 175},
        {"label": _("SINV Outstanding (Base CCY)"),  "fieldname": "sinv_outstanding",    "fieldtype": "Currency", "options": "currency", "width": 185},
        {"label": _("SINV Count"),                   "fieldname": "sinv_count",          "fieldtype": "Int",                             "width": 90},
        {"label": _("PINV Purchases (Base CCY)"),    "fieldname": "pinv_value",          "fieldtype": "Currency", "options": "currency", "width": 175},
        {"label": _("PINV Paid (Base CCY)"),         "fieldname": "pinv_paid",           "fieldtype": "Currency", "options": "currency", "width": 160},
        {"label": _("PINV Outstanding (Base CCY)"),  "fieldname": "pinv_outstanding",    "fieldtype": "Currency", "options": "currency", "width": 185},
        {"label": _("PINV Count"),                   "fieldname": "pinv_count",          "fieldtype": "Int",                             "width": 85},
        {"label": _("Expense Claims"),               "fieldname": "exp_value",           "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": _("Exp Reimbursed"),               "fieldname": "exp_paid",            "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": _("Exp Pending"),                  "fieldname": "exp_pending",         "fieldtype": "Currency", "options": "currency", "width": 130},
        {"label": _("Exp Count"),                    "fieldname": "exp_count",           "fieldtype": "Int",                             "width": 85},
        {"label": _("Stock / Materials Cost"),       "fieldname": "stock_value",         "fieldtype": "Currency", "options": "currency", "width": 165},
        {"label": _("STE Count"),                    "fieldname": "ste_count",           "fieldtype": "Int",                             "width": 85},
        {"label": _("Total Costs (Base CCY)"),       "fieldname": "total_costs",         "fieldtype": "Currency", "options": "currency", "width": 160},
        {"label": _("Gross Margin (Base CCY)"),      "fieldname": "gross_margin",        "fieldtype": "Currency", "options": "currency", "width": 165},
        {"label": _("Margin %"),                     "fieldname": "margin_pct",          "fieldtype": "Percent",                         "width": 90},
        {"label": _("Start Date"),                   "fieldname": "expected_start_date", "fieldtype": "Date",                            "width": 110},
        {"label": _("End Date"),                     "fieldname": "expected_end_date",   "fieldtype": "Date",                            "width": 110},
        {"label": _("Days Remaining"),               "fieldname": "days_remaining",      "fieldtype": "Int",                             "width": 120},
        {"label": _("Timeline Status"),              "fieldname": "timeline_status",     "fieldtype": "Data",                            "width": 130},
        {"label": _("Currency"),                     "fieldname": "currency",            "fieldtype": "Data",     "hidden": 1,           "width": 80},
    ]


def get_data(filters):
    conditions, filter_values = get_conditions(filters)
    rows = frappe.db.sql("""
        SELECT
            p.name                                AS project,
            p.project_name,
            p.customer,
            p.status,
            COALESCE(p.percent_complete, 0)       AS percent_complete,
            p.expected_start_date,
            p.expected_end_date,
            comp.default_currency                 AS currency,
            COALESCE(so_agg.so_value,    0)       AS so_value,
            COALESCE(so_agg.so_count,    0)       AS so_count,
            COALESCE(sinv_agg.sinv_value,0)       AS sinv_value,
            COALESCE(sinv_agg.sinv_paid, 0)       AS sinv_paid,
            COALESCE(sinv_agg.sinv_out,  0)       AS sinv_outstanding,
            COALESCE(sinv_agg.sinv_count,0)       AS sinv_count,
            COALESCE(pinv_agg.pinv_value,0)       AS pinv_value,
            COALESCE(pinv_agg.pinv_paid, 0)       AS pinv_paid,
            COALESCE(pinv_agg.pinv_out,  0)       AS pinv_outstanding,
            COALESCE(pinv_agg.pinv_count,0)       AS pinv_count,
            COALESCE(exp_agg.exp_value,  0)       AS exp_value,
            COALESCE(exp_agg.exp_paid,   0)       AS exp_paid,
            COALESCE(exp_agg.exp_count,  0)       AS exp_count,
            COALESCE(ste_agg.stock_value,0)       AS stock_value,
            COALESCE(ste_agg.ste_count,  0)       AS ste_count
        FROM `tabProject` p
        JOIN `tabCompany` comp ON comp.name = p.company
        LEFT JOIN (
            SELECT project, SUM(base_net_total) AS so_value, COUNT(name) AS so_count
            FROM `tabSales Order`
            WHERE docstatus = 1 AND project IS NOT NULL AND project != ''
            GROUP BY project
        ) so_agg ON so_agg.project = p.name
        LEFT JOIN (
            SELECT project,
                SUM(base_net_total)                               AS sinv_value,
                SUM(GREATEST(base_grand_total - CASE WHEN party_account_currency = 'TZS' THEN outstanding_amount ELSE outstanding_amount * COALESCE(conversion_rate, 1) END, 0)) AS sinv_paid,
                SUM(LEAST(CASE WHEN party_account_currency = 'TZS' THEN outstanding_amount ELSE outstanding_amount * COALESCE(conversion_rate, 1) END, base_grand_total))        AS sinv_out,
                COUNT(name)                                       AS sinv_count
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND project IS NOT NULL AND project != ''
            GROUP BY project
        ) sinv_agg ON sinv_agg.project = p.name
        LEFT JOIN (
            SELECT project,
                SUM(base_net_total)                               AS pinv_value,
                SUM(CASE WHEN (base_grand_total - CASE WHEN party_account_currency = 'TZS' THEN outstanding_amount ELSE outstanding_amount * COALESCE(conversion_rate, 1) END) > 1 THEN (base_grand_total - CASE WHEN party_account_currency = 'TZS' THEN outstanding_amount ELSE outstanding_amount * COALESCE(conversion_rate, 1) END) ELSE 0 END) AS pinv_paid,
                SUM(CASE WHEN party_account_currency = 'TZS' THEN outstanding_amount ELSE outstanding_amount * COALESCE(conversion_rate, 1) END)                                 AS pinv_out,
                COUNT(name)                                       AS pinv_count
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 AND project IS NOT NULL AND project != ''
            GROUP BY project
        ) pinv_agg ON pinv_agg.project = p.name
        LEFT JOIN (
            SELECT project,
                SUM(total_claimed_amount)    AS exp_value,
                SUM(total_amount_reimbursed) AS exp_paid,
                COUNT(name)                  AS exp_count
            FROM `tabExpense Claim`
            WHERE docstatus = 1 AND project IS NOT NULL AND project != ''
            GROUP BY project
        ) exp_agg ON exp_agg.project = p.name
        LEFT JOIN (
            SELECT se.project,
                SUM(sed.amount)         AS stock_value,
                COUNT(DISTINCT se.name) AS ste_count
            FROM `tabStock Entry` se
            INNER JOIN `tabStock Entry Detail` sed
                ON sed.parent = se.name AND sed.t_warehouse IS NULL
            WHERE se.docstatus = 1
              AND se.project IS NOT NULL AND se.project != ''
              AND se.stock_entry_type IN (
                  'Material Issue',
                  'Material Transfer for Manufacture',
                  'Manufacture',
                  'Send to Subcontractor')
            GROUP BY se.project
        ) ste_agg ON ste_agg.project = p.name
        WHERE 1=1
          {conditions}
        ORDER BY p.creation DESC
    """.format(conditions=conditions), filter_values, as_dict=True)

    today = nowdate()
    for row in rows:
        row["exp_pending"] = flt(row.exp_value) - flt(row.exp_paid)
        row["total_costs"] = flt(row.pinv_value) + flt(row.exp_value) + flt(row.stock_value)

        # Margin basis: SO for open/cancelled, SINV for completed
        if row["status"] == "Completed":
            margin_basis = flt(row.sinv_value)
        else:
            margin_basis = flt(row.so_value)

        row["gross_margin"] = margin_basis - row["total_costs"]
        row["margin_pct"] = (row["gross_margin"] / margin_basis * 100) if margin_basis else 0.0
        row["days_remaining"] = date_diff(row.expected_end_date, today) if row.expected_end_date else None

        if row["status"] == "Completed":
            row["timeline_status"] = "Done"
        elif row["status"] == "Cancelled":
            row["timeline_status"] = "N/A"
        elif row["days_remaining"] is None:
            row["timeline_status"] = "No end date"
        elif row["days_remaining"] < 0:
            row["timeline_status"] = str(abs(row["days_remaining"])) + "d overdue"
        elif row["days_remaining"] == 0:
            row["timeline_status"] = "Due today"
        else:
            row["timeline_status"] = str(row["days_remaining"]) + "d left"

    return rows


def get_conditions(filters):
    conditions, values = [], {}
    if filters.get("company"):
        conditions.append("AND p.company = %(company)s")
        values["company"] = filters["company"]
    if filters.get("status"):
        conditions.append("AND p.status = %(status)s")
        values["status"] = filters["status"]
    if filters.get("customer"):
        conditions.append("AND p.customer = %(customer)s")
        values["customer"] = filters["customer"]
    if filters.get("project"):
        projects = [p.strip() for p in filters["project"].split(",") if p.strip()]
        if len(projects) == 1:
            conditions.append("AND p.name = %(project)s")
            values["project"] = projects[0]
        else:
            placeholders = ", ".join(["%(project_{})s".format(i) for i in range(len(projects))])
            conditions.append("AND p.name IN ({})".format(placeholders))
            for i, proj in enumerate(projects):
                values["project_{}".format(i)] = proj
    if filters.get("from_date"):
        conditions.append("AND p.expected_start_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("AND p.expected_end_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("overdue_only"):
        conditions.append("AND p.expected_end_date < %(today)s AND p.status = 'Open'")
        values["today"] = nowdate()
    return " ".join(conditions), values


def get_report_summary(data):
    if not data:
        return []
    total_so     = sum(flt(r.get("so_value",     0)) for r in data)
    total_billed = sum(flt(r.get("sinv_value",   0)) for r in data)
    total_costs  = sum(flt(r.get("total_costs",  0)) for r in data)
    total_margin = sum(flt(r.get("gross_margin", 0)) for r in data)
    overdue = 0
    for r in data:
        if r.get("status") == "Open" and r.get("days_remaining") is not None and r["days_remaining"] < 0:
            overdue += 1
    margin_basis_total = sum(
        flt(r.get("sinv_value", 0)) if r.get("status") == "Completed"
        else flt(r.get("so_value", 0))
        for r in data
    )
    margin_pct    = (total_margin / margin_basis_total * 100) if margin_basis_total else 0
    margin_color  = "green" if total_margin >= 0 else "red"
    pct_color     = "green" if margin_pct >= 15 else "orange"
    overdue_color = "red" if overdue else "green"
    return [
        {"value": len(data),           "label": _("Total Projects"),   "datatype": "Int",      "color": "blue"},
        {"value": total_so,            "label": _("Total SO Value"),    "datatype": "Currency", "color": "blue"},
        {"value": total_billed,        "label": _("Total SINV Billed"), "datatype": "Currency", "color": "green"},
        {"value": total_costs,         "label": _("Total Costs"),       "datatype": "Currency", "color": "orange"},
        {"value": total_margin,        "label": _("Gross Margin"),      "datatype": "Currency", "color": margin_color},
        {"value": round(margin_pct,1), "label": _("Margin %"),          "datatype": "Percent",  "color": pct_color},
        {"value": overdue,             "label": _("Overdue Projects"),  "datatype": "Int",      "color": overdue_color},
    ]


def get_chart(data):
    if not data:
        return {}
    top10 = sorted(
        [r for r in data if r.get("so_value", 0) > 0],
        key=lambda r: r["so_value"],
        reverse=True
    )[:10]
    if not top10:
        return {}
    return {
        "data": {
            "labels": [cstr(r.get("project", "")) for r in top10],
            "datasets": [
                {"name": _("SO Value"),    "values": [flt(r.get("so_value",    0)) for r in top10], "chartType": "bar"},
                {"name": _("SINV Billed"), "values": [flt(r.get("sinv_value",  0)) for r in top10], "chartType": "bar"},
                {"name": _("Total Costs"), "values": [flt(r.get("total_costs", 0)) for r in top10], "chartType": "bar"},
            ],
        },
        "type": "bar",
        "colors": ["#378ADD", "#3B6D11", "#BA7517"],
        "barOptions": {"stacked": 0},
        "axisOptions": {"xIsSeries": True},
        "height": 280,
    }
