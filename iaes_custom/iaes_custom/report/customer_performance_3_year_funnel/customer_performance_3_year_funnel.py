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
        {
            "label": _("Customer"),
            "fieldname": "customer",
            "fieldtype": "Data",
            "width": 240,
        }
    ]

    for year in years:
        columns.extend([
            {
                "label": _("{0} OPTY").format(year),
                "fieldname": f"opty_{year}",
                "fieldtype": "Int",
                "width": 85,
            },
            {
                "label": _("{0} QTN").format(year),
                "fieldname": f"qtn_{year}",
                "fieldtype": "Int",
                "width": 85,
            },
            {
                "label": _("{0} SO").format(year),
                "fieldname": f"so_{year}",
                "fieldtype": "Int",
                "width": 85,
            },
            {
                "label": _("{0} SO Value").format(year),
                "fieldname": f"so_val_{year}",
                "fieldtype": "Currency",
                "width": 120,
            },
            {
                "label": _("{0} Conv %").format(year),
                "fieldname": f"conv_{year}",
                "fieldtype": "Percent",
                "width": 95,
            },
        ])

    return columns


def get_data(filters, years):
    customer_map = {}

    def ensure_customer(customer):
        if not customer:
            return None

        customer = str(customer).strip()
        if not customer:
            return None

        if customer not in customer_map:
            row = {"customer": customer}
            for y in years:
                row[f"opty_{y}"] = 0
                row[f"qtn_{y}"] = 0
                row[f"so_{y}"] = 0
                row[f"so_val_{y}"] = 0
                row[f"conv_{y}"] = 0
            customer_map[customer] = row

        return customer_map[customer]

    for r in get_transaction_data("Opportunity", "party_name", filters, years):
        row = ensure_customer(r.customer)
        if row:
            row[f"opty_{r.year}"] = cint(r.cnt)

    for r in get_transaction_data("Quotation", "party_name", filters, years):
        row = ensure_customer(r.customer)
        if row:
            row[f"qtn_{r.year}"] = cint(r.cnt)

    for r in get_transaction_data("Sales Order", "customer", filters, years, amount_field="net_total"):
        row = ensure_customer(r.customer)
        if row:
            row[f"so_{r.year}"] = cint(r.cnt)
            row[f"so_val_{r.year}"] = flt(r.amount)

    data = []
    for customer, row in customer_map.items():
        has_activity = False

        for y in years:
            opty = cint(row.get(f"opty_{y}", 0))
            so = cint(row.get(f"so_{y}", 0))

            row[f"conv_{y}"] = round((so / opty * 100), 2) if opty > 0 else 0

            if opty or cint(row.get(f"qtn_{y}", 0)) or so:
                has_activity = True

        if has_activity:
            data.append(row)

    latest_year = years[-1]
    data.sort(
        key=lambda x: (
            -flt(x.get(f"so_val_{latest_year}", 0)),
            -cint(x.get(f"so_{latest_year}", 0)),
            (x.get("customer") or "").lower()
        )
    )

    if data:
        total_row = {"customer": "TOTAL"}
        for y in years:
            total_row[f"opty_{y}"] = sum(cint(d.get(f"opty_{y}", 0)) for d in data)
            total_row[f"qtn_{y}"] = sum(cint(d.get(f"qtn_{y}", 0)) for d in data)
            total_row[f"so_{y}"] = sum(cint(d.get(f"so_{y}", 0)) for d in data)
            total_row[f"so_val_{y}"] = sum(flt(d.get(f"so_val_{y}", 0)) for d in data)

            total_opty = total_row[f"opty_{y}"]
            total_so = total_row[f"so_{y}"]
            total_row[f"conv_{y}"] = round((total_so / total_opty * 100), 2) if total_opty > 0 else 0

        data.append(total_row)

    return data


def get_transaction_data(doctype, customer_field, filters, years, amount_field=None):
    conditions = [
        f"YEAR(transaction_date) IN ({','.join([str(y) for y in years])})",
        "docstatus < 2",
        f"{customer_field} IS NOT NULL",
        f"{customer_field} != ''",
    ]
    params = {}

    if doctype == "Opportunity":
        conditions.append(
            "status IN ('Open', 'Replied', 'Converted', 'Won', 'Lost', 'Closed', 'Quotation', 'In preparation', 'In Preparation')"
        )

    if filters.get("customer"):
        conditions.append(f"{customer_field} = %(customer)s")
        params["customer"] = filters.get("customer")

    join_customer = ""
    if filters.get("territory") or filters.get("customer_group"):
        join_customer = f"JOIN `tabCustomer` cust ON cust.name = doct.{customer_field}"

        if filters.get("territory"):
            conditions.append("cust.territory = %(territory)s")
            params["territory"] = filters.get("territory")

        if filters.get("customer_group"):
            conditions.append("cust.customer_group = %(customer_group)s")
            params["customer_group"] = filters.get("customer_group")

    amount_sql = f", SUM({amount_field}) AS amount" if amount_field else ", 0 AS amount"

    return frappe.db.sql(f"""
        SELECT
            {customer_field} AS customer,
            YEAR(transaction_date) AS year,
            COUNT(DISTINCT name) AS cnt
            {amount_sql}
        FROM `tab{doctype}` doct
        {join_customer}
        WHERE {" AND ".join(conditions)}
        GROUP BY {customer_field}, YEAR(transaction_date)
        ORDER BY {customer_field}, YEAR(transaction_date)
    """, params, as_dict=True)


def get_chart(data, years):
    rows = [d for d in data if d.get("customer") != "TOTAL"]
    if not rows:
        return None

    labels = [str(y) for y in years]
    opty_series = []
    qtn_series = []
    so_series = []

    for y in years:
        opty_series.append(sum(cint(d.get(f"opty_{y}", 0)) for d in rows))
        qtn_series.append(sum(cint(d.get(f"qtn_{y}", 0)) for d in rows))
        so_series.append(sum(cint(d.get(f"so_{y}", 0)) for d in rows))

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Opportunities", "values": opty_series},
                {"name": "Quotations", "values": qtn_series},
                {"name": "Sales Orders", "values": so_series},
            ]
        },
        "type": "bar",
        "height": 280,
    }


def get_summary(data, years):
    rows = [d for d in data if d.get("customer") != "TOTAL"]
    if not rows:
        return []

    total_opty = 0
    total_qtn = 0
    total_so = 0
    total_so_val = 0

    for y in years:
        total_opty += sum(cint(d.get(f"opty_{y}", 0)) for d in rows)
        total_qtn += sum(cint(d.get(f"qtn_{y}", 0)) for d in rows)
        total_so += sum(cint(d.get(f"so_{y}", 0)) for d in rows)
        total_so_val += sum(flt(d.get(f"so_val_{y}", 0)) for d in rows)

    overall_conv = round((total_so / total_opty * 100), 2) if total_opty > 0 else 0

    return [
        {
            "value": total_opty,
            "label": _("Total Opportunities"),
            "datatype": "Int",
        },
        {
            "value": total_qtn,
            "label": _("Total Quotations"),
            "datatype": "Int",
        },
        {
            "value": total_so,
            "label": _("Total Sales Orders"),
            "datatype": "Int",
        },
        {
            "value": total_so_val,
            "label": _("Total SO Value"),
            "datatype": "Currency",
        },
        {
            "value": overall_conv,
            "label": _("Overall Conversion %"),
            "datatype": "Percent",
        },
    ]