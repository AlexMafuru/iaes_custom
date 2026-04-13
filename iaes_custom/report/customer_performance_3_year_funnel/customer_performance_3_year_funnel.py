import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

def execute(filters=None):
    filters = filters or {}
    years = get_years(filters)

    columns = get_columns(years)
    data = get_data(filters, years)
    chart = get_chart(data, years)
    summary = get_summary(data, years)

    return columns, data, None, chart, summary

def get_years(filters):
    from_year = cint(filters.get("from_year"))
    to_year = cint(filters.get("to_year"))

    if from_year and to_year and to_year >= from_year:
        return list(range(from_year, to_year + 1))

    current_year = getdate().year
    return [current_year - 2, current_year - 1, current_year]

def get_columns(years):
    columns = [
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 220}
    ]

    for year in years:
        columns.extend([
            {"label": _("{0} Opty").format(year), "fieldname": f"opty_{year}", "fieldtype": "Int", "width": 80},
            {"label": _("{0} Qtn").format(year), "fieldname": f"qtn_{year}", "fieldtype": "Int", "width": 80},
            {"label": _("{0} SO").format(year), "fieldname": f"so_{year}", "fieldtype": "Int", "width": 80},
            {"label": _("{0} SO Value").format(year), "fieldname": f"so_val_{year}", "fieldtype": "Currency", "width": 110},
            {"label": _("{0} Conv %").format(year), "fieldname": f"conv_{year}", "fieldtype": "Percent", "width": 90},
        ])
    return columns

def get_data(filters, years):
    customer_map = {}

    def ensure_customer(cust_name):
        if not cust_name: return None
        if cust_name not in customer_map:
            row = {"customer": cust_name}
            for y in years:
                row.update({f"opty_{y}": 0, f"qtn_{y}": 0, f"so_{y}": 0, f"so_val_{y}": 0, f"conv_{y}": 0})
            customer_map[cust_name] = row
        return customer_map[cust_name]

    # Fetch Data from various sources
    for r in get_transaction_data("Opportunity", "party_name", filters, years):
        row = ensure_customer(r.customer)
        if row: row[f"opty_{r.year}"] = r.cnt

    for r in get_transaction_data("Quotation", "party_name", filters, years):
        row = ensure_customer(r.customer)
        if row: row[f"qtn_{r.year}"] = r.cnt

    for r in get_transaction_data("Sales Order", "customer", filters, years, amount_field="net_total"):
        row = ensure_customer(r.customer)
        if row:
            row[f"so_{r.year}"] = r.cnt
            row[f"so_val_{r.year}"] = flt(r.amount)

    data = []
    for cust, row in customer_map.items():
        has_activity = False
        for y in years:
            opty = row.get(f"opty_{y}", 0)
            so = row.get(f"so_{y}", 0)
            row[f"conv_{y}"] = (so / opty * 100) if opty > 0 else 0
            if opty or so or row.get(f"qtn_{y}", 0):
                has_activity = True
        
        if has_activity:
            data.append(row)

    # Sort by latest year SO Value descending
    latest_year = years[-1]
    data.sort(key=lambda x: x.get(f"so_val_{latest_year}", 0), reverse=True)

    return data

def get_transaction_data(doctype, customer_field, filters, years, amount_field=None):
    conditions = [f"YEAR(transaction_date) IN ({','.join([str(y) for y in years])})", "docstatus < 2"]
    params = {}

    if filters.get("customer"):
        conditions.append(f"{customer_field} = %(customer)s")
        params["customer"] = filters.get("customer")

    # Joins for Territory/Group filters
    join_customer = ""
    if filters.get("territory") or filters.get("customer_group"):
        join_customer = "JOIN `tabCustomer` cust ON cust.name = doct.{}".format(customer_field)
        if filters.get("territory"):
            conditions.append("cust.territory = %(territory)s")
            params["territory"] = filters.get("territory")
        if filters.get("customer_group"):
            conditions.append("cust.customer_group = %(customer_group)s")
            params["customer_group"] = filters.get("customer_group")

    amount_sql = f", SUM({amount_field}) as amount" if amount_field else ""

    return frappe.db.sql(f"""
        SELECT 
            {customer_field} as customer, 
            YEAR(transaction_date) as year, 
            COUNT(name) as cnt 
            {amount_sql}
        FROM `tab{doctype}` doct
        {join_customer}
        WHERE {" AND ".join(conditions)}
        GROUP BY {customer_field}, YEAR(transaction_date)
    """, params, as_dict=True)

def get_chart(data, years):
    if not data: return None
    labels = [str(y) for y in years]
    opty_series, so_series = [], []

    for y in years:
        opty_series.append(sum(d.get(f"opty_{y}", 0) for d in data))
        so_series.append(sum(d.get(f"so_{y}", 0) for d in data))

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Opportunities", "values": opty_series},
                {"name": "Sales Orders", "values": so_series}
            ]
        },
        "type": "line",
        "colors": ["#7cd6fd", "#5e64ff"]
    }

def get_summary(data, years):
    if not data: return []
    total_val = sum(d.get(f"so_val_{years[-1]}", 0) for d in data)
    return [
        {"value": total_val, "label": _("Total SO Value ({0})").format(years[-1]), "datatype": "Currency"}
    ]