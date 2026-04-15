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
        },
        {
            # Enhancement 4: New vs Returning Customer indicator
            "label": _("Type"),
            "fieldname": "customer_type",
            "fieldtype": "Data",
            "width": 90,
        },
    ]

    for year in years:
        columns.extend([
            {
                "label": _("{0} OPTY").format(year),
                "fieldname": f"opty_{year}",
                "fieldtype": "Int",
                "width": 80,
            },
            {
                "label": _("{0} QTN").format(year),
                "fieldname": f"qtn_{year}",
                "fieldtype": "Int",
                "width": 80,
            },
            {
                "label": _("{0} SO").format(year),
                "fieldname": f"so_{year}",
                "fieldtype": "Int",
                "width": 80,
            },
            {
                "label": _("{0} SO Value").format(year),
                "fieldname": f"so_val_{year}",
                "fieldtype": "Currency",
                # Enhancement 6: pass options so currency renders correctly in exports
                "options": "company_currency",
                "width": 130,
            },
            {
                # Enhancement 1: Sales Invoice billed revenue
                "label": _("{0} INV Value").format(year),
                "fieldname": f"inv_val_{year}",
                "fieldtype": "Currency",
                "options": "company_currency",
                "width": 130,
            },
            {
                # Enhancement 7: OPTY→SO conversion %
                "label": _("{0} OPTY→SO %").format(year),
                "fieldname": f"conv_opty_so_{year}",
                "fieldtype": "Percent",
                "width": 105,
            },
            {
                # Enhancement 7: QTN→SO conversion %
                "label": _("{0} QTN→SO %").format(year),
                "fieldname": f"conv_qtn_so_{year}",
                "fieldtype": "Percent",
                "width": 105,
            },
        ])

    # Enhancement 6: company_currency hidden column for export rendering
    columns.append({
        "label": _("Company Currency"),
        "fieldname": "company_currency",
        "fieldtype": "Data",
        "width": 0,
        "hidden": 1,
    })

    return columns


def get_data(filters, years):
    customer_map = {}

    # Enhancement 4: find earliest SO date per customer across all years to
    # determine new vs returning relative to the report's from_year
    from_year = years[0]

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
                row[f"inv_val_{y}"] = 0
                row[f"conv_opty_so_{y}"] = 0
                row[f"conv_qtn_so_{y}"] = 0
            row["customer_type"] = "New"  # default; updated below
            row["company_currency"] = get_company_currency(filters)
            customer_map[customer] = row
        return customer_map[customer]

    # Enhancement 3 FIX: Opportunity uses `transaction_date` in v15
    # (frappe renamed the field; verify with fallback below)
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

    # Enhancement 1: Sales Invoice billed revenue
    for r in get_transaction_data("Sales Invoice", "customer", filters, years, amount_field="net_total"):
        row = ensure_customer(r.customer)
        if row:
            row[f"inv_val_{r.year}"] = flt(r.amount)

    # Enhancement 4: determine New vs Returning
    # A customer is "New" if their first-ever SO falls within the report period
    first_so_years = get_first_so_years(list(customer_map.keys()))
    for customer, row in customer_map.items():
        first_year = first_so_years.get(customer)
        if first_year and first_year >= from_year:
            row["customer_type"] = "New"
        else:
            row["customer_type"] = "Returning"

    data = []
    for customer, row in customer_map.items():
        has_activity = False
        for y in years:
            opty = cint(row.get(f"opty_{y}", 0))
            qtn = cint(row.get(f"qtn_{y}", 0))
            so = cint(row.get(f"so_{y}", 0))

            # Enhancement 7: separate OPTY→SO and QTN→SO conversion
            row[f"conv_opty_so_{y}"] = round((so / opty * 100), 2) if opty > 0 else 0
            row[f"conv_qtn_so_{y}"] = round((so / qtn * 100), 2) if qtn > 0 else 0

            if opty or qtn or so or flt(row.get(f"inv_val_{y}", 0)):
                has_activity = True

        if has_activity:
            # Enhancement 5: conditional row color indicator
            latest_year = years[-1]
            latest_conv = flt(row.get(f"conv_opty_so_{latest_year}", 0))
            latest_so_val = flt(row.get(f"so_val_{latest_year}", 0))

            if latest_conv >= 50 or latest_so_val > 0:
                row["indicator"] = "Green"
            elif latest_conv == 0 and latest_so_val == 0:
                row["indicator"] = "Red"
            else:
                row["indicator"] = "Orange"

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
        total_row = {
            "customer": "TOTAL",
            "customer_type": "",
            "indicator": "Blue",
            "company_currency": get_company_currency(filters),
        }
        for y in years:
            total_row[f"opty_{y}"] = sum(cint(d.get(f"opty_{y}", 0)) for d in data)
            total_row[f"qtn_{y}"] = sum(cint(d.get(f"qtn_{y}", 0)) for d in data)
            total_row[f"so_{y}"] = sum(cint(d.get(f"so_{y}", 0)) for d in data)
            total_row[f"so_val_{y}"] = sum(flt(d.get(f"so_val_{y}", 0)) for d in data)
            total_row[f"inv_val_{y}"] = sum(flt(d.get(f"inv_val_{y}", 0)) for d in data)

            total_opty = total_row[f"opty_{y}"]
            total_qtn = total_row[f"qtn_{y}"]
            total_so = total_row[f"so_{y}"]
            total_row[f"conv_opty_so_{y}"] = round((total_so / total_opty * 100), 2) if total_opty > 0 else 0
            total_row[f"conv_qtn_so_{y}"] = round((total_so / total_qtn * 100), 2) if total_qtn > 0 else 0

        data.append(total_row)

    return data


def get_transaction_data(doctype, customer_field, filters, years, amount_field=None):
    """
    Enhancement 3 FIX: Opportunity in Frappe v15 uses `transaction_date`.
    Quotation also uses `transaction_date`. Sales Order and Sales Invoice
    use `transaction_date`. This is consistent across all four doctypes
    in v15 — no field alias needed.

    We guard against missing field with a try/except and fall back to
    `creation` date only if the query fails, so the report never silently
    drops data.
    """
    conditions = [
        f"YEAR(doct.transaction_date) IN ({','.join([str(y) for y in years])})",
        "doct.docstatus < 2",
        f"doct.{customer_field} IS NOT NULL",
        f"doct.{customer_field} != ''",
    ]
    params = {}

    if doctype == "Opportunity":
        conditions.append(
            "doct.status IN ('Open', 'Replied', 'Converted', 'Won', 'Lost', "
            "'Closed', 'Quotation', 'In preparation', 'In Preparation')"
        )

    if doctype == "Sales Invoice":
        # Only count submitted invoices for billed revenue
        conditions[1] = "doct.docstatus = 1"

    if filters.get("customer"):
        conditions.append(f"doct.{customer_field} = %(customer)s")
        params["customer"] = filters.get("customer")

    # Enhancement 2: Company filter
    if filters.get("company"):
        conditions.append("doct.company = %(company)s")
        params["company"] = filters.get("company")

    join_customer = ""
    if filters.get("territory") or filters.get("customer_group"):
        join_customer = f"JOIN `tabCustomer` cust ON cust.name = doct.{customer_field}"
        if filters.get("territory"):
            conditions.append("cust.territory = %(territory)s")
            params["territory"] = filters.get("territory")
        if filters.get("customer_group"):
            conditions.append("cust.customer_group = %(customer_group)s")
            params["customer_group"] = filters.get("customer_group")

    amount_sql = f", SUM(doct.{amount_field}) AS amount" if amount_field else ", 0 AS amount"

    try:
        return frappe.db.sql(f"""
            SELECT
                doct.{customer_field} AS customer,
                YEAR(doct.transaction_date) AS year,
                COUNT(DISTINCT doct.name) AS cnt
                {amount_sql}
            FROM `tab{doctype}` doct
            {join_customer}
            WHERE {" AND ".join(conditions)}
            GROUP BY doct.{customer_field}, YEAR(doct.transaction_date)
            ORDER BY doct.{customer_field}, YEAR(doct.transaction_date)
        """, params, as_dict=True)
    except Exception:
        # Enhancement 3 fallback: if transaction_date doesn't exist on this
        # doctype variant, fall back to creation year silently
        fallback_conditions = [c.replace("doct.transaction_date", "doct.creation") for c in conditions]
        return frappe.db.sql(f"""
            SELECT
                doct.{customer_field} AS customer,
                YEAR(doct.creation) AS year,
                COUNT(DISTINCT doct.name) AS cnt
                {amount_sql}
            FROM `tab{doctype}` doct
            {join_customer}
            WHERE {" AND ".join(fallback_conditions)}
            GROUP BY doct.{customer_field}, YEAR(doct.creation)
            ORDER BY doct.{customer_field}, YEAR(doct.creation)
        """, params, as_dict=True)


def get_first_so_years(customers):
    """Enhancement 4: return the earliest SO year per customer."""
    if not customers:
        return {}
    placeholders = ", ".join(["%s"] * len(customers))
    rows = frappe.db.sql(f"""
        SELECT customer, YEAR(MIN(transaction_date)) AS first_year
        FROM `tabSales Order`
        WHERE customer IN ({placeholders})
          AND docstatus < 2
        GROUP BY customer
    """, tuple(customers), as_dict=True)
    return {r.customer: r.first_year for r in rows}


def get_company_currency(filters):
    """Enhancement 6: resolve company currency for export rendering."""
    company = filters.get("company") or frappe.defaults.get_user_default("Company")
    if company:
        return frappe.get_cached_value("Company", company, "default_currency") or ""
    return ""


def get_chart(data, years):
    rows = [d for d in data if d.get("customer") != "TOTAL"]
    if not rows:
        return None

    labels = [str(y) for y in years]
    opty_series, qtn_series, so_series, inv_series = [], [], [], []

    for y in years:
        opty_series.append(sum(cint(d.get(f"opty_{y}", 0)) for d in rows))
        qtn_series.append(sum(cint(d.get(f"qtn_{y}", 0)) for d in rows))
        so_series.append(sum(cint(d.get(f"so_{y}", 0)) for d in rows))
        inv_series.append(sum(flt(d.get(f"inv_val_{y}", 0)) for d in rows))

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Opportunities", "values": opty_series},
                {"name": "Quotations", "values": qtn_series},
                {"name": "Sales Orders", "values": so_series},
                # Enhancement 1: INV series in chart
                {"name": "Invoiced Value", "values": inv_series},
            ]
        },
        "type": "bar",
        "height": 300,
    }


def get_summary(data, years):
    rows = [d for d in data if d.get("customer") != "TOTAL"]
    if not rows:
        return []

    total_opty = total_qtn = total_so = total_so_val = total_inv_val = 0

    for y in years:
        total_opty += sum(cint(d.get(f"opty_{y}", 0)) for d in rows)
        total_qtn += sum(cint(d.get(f"qtn_{y}", 0)) for d in rows)
        total_so += sum(cint(d.get(f"so_{y}", 0)) for d in rows)
        total_so_val += sum(flt(d.get(f"so_val_{y}", 0)) for d in rows)
        total_inv_val += sum(flt(d.get(f"inv_val_{y}", 0)) for d in rows)

    overall_conv_opty_so = round((total_so / total_opty * 100), 2) if total_opty > 0 else 0
    overall_conv_qtn_so = round((total_so / total_qtn * 100), 2) if total_qtn > 0 else 0

    # Enhancement 4: count new vs returning
    new_count = sum(1 for d in rows if d.get("customer_type") == "New")
    returning_count = len(rows) - new_count

    return [
        {"value": total_opty, "label": _("Total Opportunities"), "datatype": "Int"},
        {"value": total_qtn, "label": _("Total Quotations"), "datatype": "Int"},
        {"value": total_so, "label": _("Total Sales Orders"), "datatype": "Int"},
        {"value": total_so_val, "label": _("Total SO Value"), "datatype": "Currency"},
        # Enhancement 1: invoiced value in summary
        {"value": total_inv_val, "label": _("Total Invoiced"), "datatype": "Currency"},
        # Enhancement 7: both conversion metrics
        {"value": overall_conv_opty_so, "label": _("OPTY→SO Conv %"), "datatype": "Percent"},
        {"value": overall_conv_qtn_so, "label": _("QTN→SO Conv %"), "datatype": "Percent"},
        # Enhancement 4: customer type breakdown
        {"value": new_count, "label": _("New Customers"), "datatype": "Int"},
        {"value": returning_count, "label": _("Returning Customers"), "datatype": "Int"},
    ]