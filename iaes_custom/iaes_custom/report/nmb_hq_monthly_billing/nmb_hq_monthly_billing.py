"""
NMB HQ Monthly Billing — Server-side Report Logic
==================================================

Frappe Query Report. Surfaces every MREQ line for the project, computes the
full pricing analysis (cost from PINV/EXP/STE → margin test → Final Price),
and flags status so the accountant can identify what's ready to quote.

ASSUMPTIONS (patch these if wrong on first deploy):
    1. Contract Price List doctype is named exactly "Contract Price List"
       with fields: item_code, project, contract_price_vat_excl,
       effective_from, effective_to.
    2. Standard ERPNext linkage:
         - Purchase Invoice Item.material_request_item → Material Request Item.name
         - Purchase Order Item.material_request_item   → Material Request Item.name
         - Delivery Note Item.against_sales_order      → Sales Order
       and DN to MREQ via SO is handled by joining through Sales Order Item.
    3. STE has no native link to MREQ — matched on item_code + project +
       posting date in window.
    4. EXP Claim has no native link to MREQ — matched on
       Expense Claim.project + description LIKE %item_name%.
    5. Cost basis order: PINV (status='Paid') → STE valuation_rate → EXP fuzzy.
    6. 20% threshold:
         - Test:  reference_price >= cost * 1.20  (markup test)
         - Final: cost / 0.80 when generating from cost (true 20% margin)

PLACEMENT:
    /apps/<your_app>/<your_app>/<module>/report/nmb_hq_monthly_billing/
        nmb_hq_monthly_billing.py
        nmb_hq_monthly_billing.js
        nmb_hq_monthly_billing.json   (auto-created via bench)
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days


# ---------------------------------------------------------------------------
# Configuration — patch here if assumptions are wrong
# ---------------------------------------------------------------------------
CONTRACT_PRICE_DOCTYPE = "NMB Contract Price"   # exact doctype name (verified from doctype JSON)
CONTRACT_FIELD_ITEM_CODE = "item_code"
CONTRACT_FIELD_PROJECT = "project"
CONTRACT_FIELD_PRICE = "contract_unit_price"    # was contract_price_vat_excl in earlier draft
CONTRACT_FIELD_FROM = "effective_from"
CONTRACT_FIELD_TO = "effective_to"

THRESHOLD_MARKUP = 1.20  # cost * 1.20 = threshold contract price must beat
TARGET_MARGIN = 0.80     # cost / 0.80 = price giving true 20% margin


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    columns = _build_columns()
    data = _build_data(filters)

    # No persistence to MREQ Item — pricing is computed on the fly each run.
    # The MREQ remains a clean procurement document. Sell-price / margin logic
    # lives only in the report and the generated Quotation.

    return columns, data


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def _validate_filters(filters):
    if not filters.get("project"):
        frappe.throw(_("Project is required."))
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("From and To dates are required."))


# ---------------------------------------------------------------------------
# Columns — 26 columns matching the operational ledger spec
# ---------------------------------------------------------------------------
def _build_columns():
    return [
        {"label": _("No."), "fieldname": "sr_no", "fieldtype": "Int", "width": 50},
        {"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 95},
        {"label": _("Req No."), "fieldname": "approved_requisition_no", "fieldtype": "Data", "width": 110},
        {"label": _("MREQ"), "fieldname": "mreq", "fieldtype": "Link", "options": "Material Request", "width": 120},
        {"label": _("MREQ Item Row"), "fieldname": "mreq_item_name", "fieldtype": "Data", "width": 130, "hidden": 1},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
        {"label": _("Qty Ordered"), "fieldname": "qty_ordered", "fieldtype": "Float", "width": 90, "precision": 2},
        {"label": _("UoM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
        {"label": _("Scope"), "fieldname": "scope", "fieldtype": "Data", "width": 100},
        {"label": _("HQ/Zone"), "fieldname": "hq_zone", "fieldtype": "Data", "width": 100},
        {"label": _("PO"), "fieldname": "po", "fieldtype": "Data", "width": 110},
        {"label": _("PINV"), "fieldname": "pinv", "fieldtype": "Data", "width": 110},
        {"label": _("EXP"), "fieldname": "exp", "fieldtype": "Data", "width": 110},
        {"label": _("STE"), "fieldname": "ste", "fieldtype": "Data", "width": 110},
        {"label": _("PREC"), "fieldname": "prec", "fieldtype": "Data", "width": 110},
        {"label": _("Dnote No."), "fieldname": "dnote", "fieldtype": "Data", "width": 110},
        {"label": _("Qty Delivered"), "fieldname": "qty_delivered", "fieldtype": "Float", "width": 90, "precision": 2},
        {"label": _("Balance"), "fieldname": "balance", "fieldtype": "Float", "width": 80, "precision": 2},
        {"label": _("Unit Cost"), "fieldname": "unit_cost", "fieldtype": "Currency", "options": "currency", "width": 110},
        {"label": _("Total Purchase"), "fieldname": "total_purchase", "fieldtype": "Currency", "options": "currency", "width": 130},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 150},
        {"label": _("Unit Sell Price"), "fieldname": "unit_sell_price", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Comments"), "fieldname": "pricing_comment", "fieldtype": "Data", "width": 220},
        {"label": _("Final Price"), "fieldname": "final_price", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": _("QTN"), "fieldname": "qtn", "fieldtype": "Link", "options": "Quotation", "width": 110},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140, "hidden": 1},
        {"label": _("Currency"), "fieldname": "currency", "fieldtype": "Data", "width": 60, "hidden": 1},
    ]


# ---------------------------------------------------------------------------
# Main data assembly
# ---------------------------------------------------------------------------
def _build_data(filters):
    mreq_lines = _fetch_mreq_lines(filters)
    if not mreq_lines:
        return []

    line_names = [line.mreq_item_name for line in mreq_lines]

    pinv_map = _fetch_pinv_for_lines(line_names)
    po_map = _fetch_po_for_lines(line_names)
    prec_map = _fetch_prec_for_lines(line_names)
    dn_map = _fetch_dn_for_lines(line_names)
    ste_map = _fetch_ste_matches(mreq_lines, filters)
    exp_map = _fetch_exp_matches(mreq_lines, filters)
    contract_map = _fetch_contract_prices(mreq_lines, filters)

    rows = []
    for i, line in enumerate(mreq_lines, start=1):
        row = _compose_row(
            i, line,
            pinv_map.get(line.mreq_item_name, {}),
            po_map.get(line.mreq_item_name, []),
            prec_map.get(line.mreq_item_name, []),
            dn_map.get(line.mreq_item_name, []),
            ste_map.get(line.mreq_item_name, []),
            exp_map.get(line.mreq_item_name, []),
            contract_map.get(line.item_code),
        )

        if filters.get("hide_quoted") and row["status"] == "Quoted":
            continue
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Source fetchers — each returns a dict keyed by Material Request Item.name
# ---------------------------------------------------------------------------
def _fetch_mreq_lines(filters):
    """All MREQ Item rows for the project in the date window."""
    extra_conditions = ""
    if filters.get("scope"):
        extra_conditions += " AND mri.custom_scope = %(scope)s"
    if filters.get("hq_or_zone"):
        extra_conditions += " AND mr.custom_hq_or_zone = %(hq_or_zone)s"

    return frappe.db.sql(f"""
        SELECT
            mr.name                               AS mreq,
            mr.transaction_date                   AS transaction_date,
            mr.custom_approved_requisition_no     AS approved_requisition_no,
            mri.name                              AS mreq_item_name,
            mri.item_code                         AS item_code,
            mri.item_name                         AS item_name,
            mri.description                       AS description,
            mri.qty                               AS qty_ordered,
            mri.uom                               AS uom,
            mri.rate                              AS mreq_rate,
            mri.custom_scope                      AS scope,
            mr.custom_hq_or_zone                  AS hq_zone,
            mri.project                           AS project,
            mri.custom_quoted_in_qtn              AS qtn
        FROM `tabMaterial Request` mr
        INNER JOIN `tabMaterial Request Item` mri ON mri.parent = mr.name
        WHERE mr.docstatus = 1
          AND mri.project = %(project)s
          AND mr.transaction_date BETWEEN %(from_date)s AND %(to_date)s
          {extra_conditions}
        ORDER BY mr.transaction_date, mr.name, mri.idx
    """, filters, as_dict=True)


def _fetch_pinv_for_lines(line_names):
    """Paid PINV item lines linked to the MREQ Item rows.
    Returns: {mreq_item_name: {pinv: 'PINV-X', rate, qty, supplier}}
    """
    if not line_names:
        return {}

    rows = frappe.db.sql("""
        SELECT
            pii.material_request_item   AS mreq_item_name,
            pi.name                     AS pinv,
            pi.supplier                 AS supplier,
            pi.posting_date             AS posting_date,
            pii.rate                    AS rate,
            pii.qty                     AS qty,
            pi.status                   AS status
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.material_request_item IN %(line_names)s
          AND pi.docstatus = 1
          AND pi.status = 'Paid'
        ORDER BY pi.posting_date DESC
    """, {"line_names": line_names}, as_dict=True)

    out = {}
    for r in rows:
        existing = out.get(r.mreq_item_name)
        if not existing:
            out[r.mreq_item_name] = {
                "pinvs": [r.pinv],
                "rate": flt(r.rate),
                "qty_paid": flt(r.qty),
                "supplier": r.supplier,
            }
        else:
            if r.pinv not in existing["pinvs"]:
                existing["pinvs"].append(r.pinv)
            existing["qty_paid"] += flt(r.qty)
    return out


def _fetch_po_for_lines(line_names):
    if not line_names:
        return {}
    rows = frappe.db.sql("""
        SELECT
            poi.material_request_item   AS mreq_item_name,
            po.name                     AS po
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE poi.material_request_item IN %(line_names)s
          AND po.docstatus = 1
    """, {"line_names": line_names}, as_dict=True)

    out = {}
    for r in rows:
        out.setdefault(r.mreq_item_name, [])
        if r.po not in out[r.mreq_item_name]:
            out[r.mreq_item_name].append(r.po)
    return out


def _fetch_prec_for_lines(line_names):
    if not line_names:
        return {}
    rows = frappe.db.sql("""
        SELECT
            pri.material_request_item   AS mreq_item_name,
            pr.name                     AS prec
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.material_request_item IN %(line_names)s
          AND pr.docstatus = 1
    """, {"line_names": line_names}, as_dict=True)

    out = {}
    for r in rows:
        out.setdefault(r.mreq_item_name, [])
        if r.prec not in out[r.mreq_item_name]:
            out[r.mreq_item_name].append(r.prec)
    return out


def _fetch_dn_for_lines(line_names):
    """Delivery Notes linked back via Sales Order chain.

    Path: MREQ Item -> SO Item (via material_request_item) -> DN Item (via against_sales_order_item)
    """
    if not line_names:
        return {}

    rows = frappe.db.sql("""
        SELECT
            soi.material_request_item   AS mreq_item_name,
            dn.name                     AS dn,
            dni.qty                     AS qty
        FROM `tabSales Order Item` soi
        INNER JOIN `tabDelivery Note Item` dni
            ON dni.so_detail = soi.name
        INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE soi.material_request_item IN %(line_names)s
          AND dn.docstatus = 1
    """, {"line_names": line_names}, as_dict=True)

    out = {}
    for r in rows:
        existing = out.setdefault(r.mreq_item_name, {"dns": [], "qty_delivered": 0})
        if r.dn not in existing["dns"]:
            existing["dns"].append(r.dn)
        existing["qty_delivered"] += flt(r.qty)

    # Convert to list-style for downstream uniformity
    return {k: v for k, v in out.items()}


def _fetch_ste_matches(mreq_lines, filters):
    """STE has no MREQ link — match by item_code + project + date window."""
    item_codes = list({line.item_code for line in mreq_lines if line.item_code})
    if not item_codes:
        return {}

    # STE Detail has 'project' via accounting dimensions or parent
    rows = frappe.db.sql("""
        SELECT
            sed.item_code           AS item_code,
            se.name                 AS ste,
            sed.qty                 AS qty,
            sed.valuation_rate      AS valuation_rate,
            se.posting_date         AS posting_date
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE sed.item_code IN %(item_codes)s
          AND se.docstatus = 1
          AND se.stock_entry_type IN ('Material Issue', 'Material Transfer')
          AND se.posting_date BETWEEN %(window_start)s AND %(window_end)s
          AND (sed.project = %(project)s OR se.project = %(project)s)
    """, {
        "item_codes": item_codes,
        "project": filters.project,
        "window_start": add_days(filters.from_date, -90),
        "window_end": filters.to_date,
    }, as_dict=True)

    out = {}
    for r in rows:
        for line in mreq_lines:
            if line.item_code != r.item_code:
                continue
            existing = out.setdefault(line.mreq_item_name, {
                "stes": [],
                "qty_issued": 0,
                "valuation_rate": None,
            })
            if r.ste not in existing["stes"]:
                existing["stes"].append(r.ste)
            existing["qty_issued"] += flt(r.qty)
            if existing["valuation_rate"] is None:
                existing["valuation_rate"] = flt(r.valuation_rate)
    return out


def _fetch_exp_matches(mreq_lines, filters):
    """EXP Claim has no MREQ link — match by project + description LIKE %item_name%."""
    item_names_by_line = {
        line.mreq_item_name: (line.item_name or "").strip()
        for line in mreq_lines
        if line.item_name
    }
    if not item_names_by_line:
        return {}

    rows = frappe.db.sql("""
        SELECT
            ec.name             AS exp,
            ecd.description     AS description,
            ecd.sanctioned_amount AS amount,
            ec.posting_date     AS posting_date
        FROM `tabExpense Claim` ec
        INNER JOIN `tabExpense Claim Detail` ecd ON ecd.parent = ec.name
        WHERE ec.docstatus = 1
          AND ec.approval_status = 'Approved'
          AND (ecd.project = %(project)s OR ec.project = %(project)s)
          AND ec.posting_date BETWEEN %(from_date)s AND %(to_date)s
    """, {
        "project": filters.project,
        "from_date": add_days(filters.from_date, -90),
        "to_date": filters.to_date,
    }, as_dict=True)

    out = {}
    for line_name, item_name in item_names_by_line.items():
        for r in rows:
            if not r.description:
                continue
            if item_name.lower() in r.description.lower() or r.description.lower() in item_name.lower():
                existing = out.setdefault(line_name, {"exps": [], "amount": 0})
                if r.exp not in existing["exps"]:
                    existing["exps"].append(r.exp)
                existing["amount"] += flt(r.amount)
    return out


def _fetch_contract_prices(mreq_lines, filters):
    """Look up each item code in the Contract Price List for this project."""
    item_codes = list({line.item_code for line in mreq_lines if line.item_code})
    if not item_codes:
        return {}

    if not frappe.db.exists("DocType", CONTRACT_PRICE_DOCTYPE):
        # Doctype not found — return empty so report still works
        frappe.log_error(
            f"Contract Price List doctype '{CONTRACT_PRICE_DOCTYPE}' not found — pricing will treat all items as off-contract.",
            "NMB Billing Report"
        )
        return {}

    table = f"tab{CONTRACT_PRICE_DOCTYPE}"
    rows = frappe.db.sql(f"""
        SELECT
            `{CONTRACT_FIELD_ITEM_CODE}`   AS item_code,
            `{CONTRACT_FIELD_PRICE}`       AS contract_price,
            `{CONTRACT_FIELD_FROM}`        AS effective_from,
            `{CONTRACT_FIELD_TO}`          AS effective_to
        FROM `{table}`
        WHERE `{CONTRACT_FIELD_ITEM_CODE}` IN %(codes)s
          AND `{CONTRACT_FIELD_PROJECT}` = %(project)s
        ORDER BY `{CONTRACT_FIELD_FROM}` DESC
    """, {"codes": item_codes, "project": filters.project}, as_dict=True)

    out = {}
    for r in rows:
        if r.item_code in out:
            continue  # already have most recent
        # Filter by effective dates if set
        if r.effective_from and getdate(r.effective_from) > getdate(filters.to_date):
            continue
        if r.effective_to and getdate(r.effective_to) < getdate(filters.from_date):
            continue
        out[r.item_code] = flt(r.contract_price)
    return out


# ---------------------------------------------------------------------------
# Row composition + pricing logic
# ---------------------------------------------------------------------------
def _compose_row(sr, line, pinv, po_list, prec_list, dn_list, ste_data, exp_data, contract_price):
    qty_ordered = flt(line.qty_ordered)

    # Cost determination: PINV → STE → EXP → 0
    cost = 0.0
    supplier = ""
    qty_paid_or_issued = 0.0

    if pinv:
        cost = flt(pinv.get("rate"))
        supplier = pinv.get("supplier") or ""
        qty_paid_or_issued = flt(pinv.get("qty_paid"))
    elif ste_data and flt(ste_data.get("valuation_rate")):
        cost = flt(ste_data["valuation_rate"])
        supplier = "Stock Issue (STE)"
        qty_paid_or_issued = flt(ste_data.get("qty_issued"))
    elif exp_data and flt(exp_data.get("amount")) and qty_ordered:
        # Estimate unit cost from EXP amount / qty ordered (rough)
        cost = flt(exp_data["amount"]) / qty_ordered
        supplier = "Cash / Expense Claim"
        qty_paid_or_issued = qty_ordered  # assume EXP covered ordered qty

    # Reference / Final price + comment
    threshold_price = cost * THRESHOLD_MARKUP
    target_price = cost / TARGET_MARGIN if cost else 0.0

    if cost <= 0:
        unit_sell_price = 0.0
        final_price = 0.0
        comment = "No cost source"
    elif contract_price is not None and contract_price > 0:
        unit_sell_price = contract_price
        if contract_price >= threshold_price:
            final_price = contract_price
            comment = "Contract – OK"
        else:
            final_price = target_price
            margin_pct = ((contract_price - cost) / contract_price * 100) if contract_price else 0
            comment = f"Below threshold (contract margin {margin_pct:.1f}%) – marked up to true 20%"
    else:
        unit_sell_price = target_price
        final_price = target_price
        comment = "Not in contract – market price + true 20% margin"

    # No accountant override branch — pricing is computed on the fly.
    # If you need to override a price, edit it on the generated Quotation
    # before submitting. The Quotation is the single source of truth for
    # the customer-facing rate.

    qty_delivered = flt(dn_list.get("qty_delivered", 0)) if isinstance(dn_list, dict) else 0
    balance = max(qty_ordered - qty_delivered, 0)

    # Status logic
    status = _compute_status(
        line=line,
        cost=cost,
        qty_paid_or_issued=qty_paid_or_issued,
        qty_delivered=qty_delivered,
    )

    total_purchase = cost * qty_ordered if cost else 0

    return {
        "sr_no": sr,
        "transaction_date": line.transaction_date,
        "approved_requisition_no": line.approved_requisition_no or "",
        "mreq": line.mreq,
        "mreq_item_name": line.mreq_item_name,
        "item_name": line.item_name or "",
        "item_code": line.item_code or "",
        "qty_ordered": qty_ordered,
        "uom": line.uom or "",
        "scope": line.scope or "",
        "hq_zone": line.hq_zone or "",
        "po": ", ".join(po_list) if po_list else "",
        "pinv": ", ".join(pinv.get("pinvs", [])) if pinv else "",
        "exp": ", ".join(exp_data.get("exps", [])) if exp_data else "",
        "ste": ", ".join(ste_data.get("stes", [])) if ste_data else "",
        "prec": ", ".join(prec_list) if prec_list else "",
        "dnote": ", ".join(dn_list.get("dns", [])) if isinstance(dn_list, dict) else "",
        "qty_delivered": qty_delivered,
        "balance": balance,
        "unit_cost": cost,
        "total_purchase": total_purchase,
        "supplier": supplier,
        "unit_sell_price": unit_sell_price,
        "pricing_comment": comment,
        "final_price": final_price,
        "status": status,
        "qtn": line.qtn or "",
        "project": line.project,
        "currency": "TZS",
    }


def _compute_status(line, cost, qty_paid_or_issued, qty_delivered):
    """Reconciliation-report status flag."""
    if line.qtn:
        return "Quoted"
    if cost <= 0:
        return "No cost source"
    if qty_delivered <= 0:
        return "DN missing"
    if qty_paid_or_issued <= 0:
        return "Not yet paid"
    return "Ready to quote"


# ---------------------------------------------------------------------------
# (No persistence layer — prices are computed on the fly each report run.
# The MREQ Item stays a clean procurement document. Single source of truth
# for cost lives in PINV / EXP Claim / STE; for sell-price lives in the
# NMB Contract Price doctype + this report's pricing logic. Any price
# override happens on the generated Quotation, not on the MREQ.)
# ---------------------------------------------------------------------------
