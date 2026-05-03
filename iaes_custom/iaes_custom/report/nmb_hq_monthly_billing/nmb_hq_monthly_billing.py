# -*- coding: utf-8 -*-
# Copyright (c) 2026, IAES and contributors
# License: MIT
#
# NMB HQ Monthly Billing — Script Report
# ---------------------------------------
# Reconciles the HQ procurement-to-invoicing flow:
#
#   Material Request (MREQ)
#       │   signed off by NMB Bank HQ
#       ▼
#   ┌──────────────────────────────────────────────────────────┐
#   │  Procurement (one of two paths):                         │
#   │    (a) Expense Claim (EXP)   — engineer reimbursement    │
#   │    (b) PO → PINV → PREC      — formal supplier invoice   │
#   └──────────────────────────────────────────────────────────┘
#       │
#       ▼
#   Delivery Note (Dnote)        — qty actually delivered to NMB site
#       │
#       ▼
#   Sales Invoice (SINV) to NMB  — billed at: actual cost + markup %
#
# Output mirrors the legacy spreadsheet (nmb_hq_report_format.xlsx) plus a
# parallel "EXP" column next to "PINV" so each row shows which procurement
# path supplied the cost. One row per Material Request Item, grouped by
# Scope, with subtotals → VAT 18% → Grand Total.
#
# IMPORTANT — field-name TODOs:
#   This file assumes a few custom fields. Confirm or adjust before deploy.
#
#     • Material Request Item.custom_scope     (Data / Select)
#         Falls back to the linked Item Group if missing.
#     • Material Request.custom_hq_or_zone     (Select: HQ / Dar Zone)
#         Splits HQ vs Dar Zone deliveries within the same report.
#     • Material Request Item.custom_part_no   (Data) — optional MFR part #.
#     • Expense Claim Detail.custom_material_request_item   (Link → MR Item)
#         Required if you want EXP-CLAIM costs to attach to the right MREQ
#         line. Without it, expense-claim spend won't appear on this report.
#     • Sales Invoice Item.material_request    (Data / Link)
#         Required for the SINV column to populate. Fallbacks are wrapped
#         in try/except so the report still loads if absent.
#
#   Search for `# TODO[fields]` to find every spot that depends on these.

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import flt, getdate, formatdate

VAT_RATE = 0.18  # 18% Tanzanian VAT

SCOPE_ORDER = ["AC", "Electrical", "Plumbing", "Generator", "Store"]


# ════════════════════════════════════════════════════════════════════════════
#   ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    columns = get_columns()
    raw_rows = _fetch_material_request_lines(filters)
    data = _build_grouped_rows(raw_rows, filters)

    return columns, data


def _validate_filters(filters):
    if not filters.get("project"):
        frappe.throw(_("Project is required."))
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("From Date and To Date are required."))
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date."))


# ════════════════════════════════════════════════════════════════════════════
#   COLUMNS
# ════════════════════════════════════════════════════════════════════════════

def get_columns():
    return [
        {"label": _("No."),               "fieldname": "no",                "fieldtype": "Data",     "width":  50},
        {"label": _("Description"),       "fieldname": "description",       "fieldtype": "Data",     "width": 260},
        {"label": _("Part No."),          "fieldname": "part_no",           "fieldtype": "Data",     "width": 100},
        {"label": _("Scope"),             "fieldname": "scope",             "fieldtype": "Data",     "width": 100},
        {"label": _("Delivery Location"), "fieldname": "delivery_location", "fieldtype": "Data",     "width": 130},
        {"label": _("HQ/Zone"),           "fieldname": "hq_or_zone",        "fieldtype": "Data",     "width":  90},
        {"label": _("Date"),              "fieldname": "date",              "fieldtype": "Date",     "width":  90},
        {"label": _("Req"),               "fieldname": "req",               "fieldtype": "Link",     "options": "Material Request", "width": 140},
        {"label": _("Qty Ordered"),       "fieldname": "qty_ordered",       "fieldtype": "Float",    "width":  90, "precision": 2},
        {"label": _("Qty Delivered"),     "fieldname": "qty_delivered",     "fieldtype": "Float",    "width": 100, "precision": 2},
        {"label": _("Balance"),           "fieldname": "balance",           "fieldtype": "Float",    "width":  80, "precision": 2},
        {"label": _("UoM"),               "fieldname": "uom",               "fieldtype": "Data",     "width":  70},
        {"label": _("Dnote No."),         "fieldname": "dnote",             "fieldtype": "Link",     "options": "Delivery Note",   "width": 140},
        {"label": _("PINV"),              "fieldname": "pinv",              "fieldtype": "Link",     "options": "Purchase Invoice","width": 140},
        {"label": _("EXP"),               "fieldname": "exp",               "fieldtype": "Link",     "options": "Expense Claim",   "width": 140},
        {"label": _("Unit Cost"),         "fieldname": "unit_cost",         "fieldtype": "Currency", "width": 110},
        {"label": _("Total Purchase"),    "fieldname": "amount",            "fieldtype": "Currency", "width": 130},
        {"label": _("Supplier"),          "fieldname": "supplier",          "fieldtype": "Link",     "options": "Supplier",        "width": 150},
        {"label": _("SINV"),              "fieldname": "sinv",              "fieldtype": "Link",     "options": "Sales Invoice",   "width": 140},
        {"label": _("Invoice Month"),     "fieldname": "invoice_month",     "fieldtype": "Data",     "width": 110},
    ]


# ════════════════════════════════════════════════════════════════════════════
#   DATA FETCH
# ════════════════════════════════════════════════════════════════════════════

def _fetch_material_request_lines(filters):
    """
    Return a flat list of dict rows, one per Material Request Item, enriched
    with delivered qty, PINV/supplier/cost, and SINV/invoice month.
    """

    # --- 1. Material Requests in scope ----------------------------------------
    mr_filters = {
        "project":          filters.project,
        "transaction_date": ["between", [filters.from_date, filters.to_date]],
        "docstatus":        1,
    }

    # TODO[fields]: rename custom_hq_or_zone if your custom field uses a
    # different fieldname.
    if filters.get("hq_or_zone"):
        mr_filters["custom_hq_or_zone"] = filters.hq_or_zone

    mrs = frappe.get_all(
        "Material Request",
        filters=mr_filters,
        fields=[
            "name",
            "transaction_date",
            "set_warehouse",
            # TODO[fields]: include only the custom fields that actually exist.
            # If "custom_hq_or_zone" doesn't exist, REMOVE it from this list
            # AND from the filter block above, otherwise frappe will raise.
            "custom_hq_or_zone",
        ],
        order_by="transaction_date asc, name asc",
    )

    if not mrs:
        return []

    mr_names = [m.name for m in mrs]
    mr_by_name = {m.name: m for m in mrs}

    # --- 2. Material Request Items ---------------------------------------------
    items = frappe.get_all(
        "Material Request Item",
        filters={"parent": ["in", mr_names]},
        fields=[
            "name",
            "parent",
            "idx",
            "item_code",
            "item_name",
            "description",
            "qty",
            "ordered_qty",      # qty already covered by PO/PINV
            "received_qty",     # qty received via Purchase Receipt
            "uom",
            "warehouse",
            # TODO[fields]: comment out any of these that don't exist in your
            # iaes_custom customisations.
            "custom_scope",
            "custom_part_no",
        ],
        order_by="parent, idx",
    )

    # --- 3. Item Group (fallback for Scope) ------------------------------------
    item_codes = list({i.item_code for i in items if i.item_code})
    item_groups = {}
    if item_codes:
        for r in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]},
            fields=["name", "item_group"],
        ):
            item_groups[r.name] = r.item_group

    # --- 4. Delivered qty + Delivery Note linkage ------------------------------
    # Match Delivery Note Items back to Material Request via the standard
    # `material_request` field on `tabDelivery Note Item`.
    delivered = {}  # key: (mr_name, item_code) → {"qty": x, "dnote": "DN-..."}
    if mr_names:
        dn_rows = frappe.db.sql("""
            SELECT
                dni.material_request          AS mr,
                dni.material_request_item     AS mri,
                dni.item_code                 AS item_code,
                dni.qty                       AS qty,
                dni.parent                    AS dnote
            FROM `tabDelivery Note Item` dni
            INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
            WHERE dni.material_request IN %(mrs)s
              AND dn.docstatus = 1
        """, {"mrs": tuple(mr_names)}, as_dict=True)

        for r in dn_rows:
            key = r.mri or (r.mr, r.item_code)
            entry = delivered.setdefault(key, {"qty": 0.0, "dnotes": []})
            entry["qty"] += flt(r.qty)
            if r.dnote not in entry["dnotes"]:
                entry["dnotes"].append(r.dnote)

    # --- 5. Purchase Invoice / supplier / unit cost ----------------------------
    purchase = {}  # key: mri name → list of {"pinv", "supplier", "rate", "amount"}
    if mr_names:
        pi_rows = frappe.db.sql("""
            SELECT
                pii.material_request          AS mr,
                pii.material_request_item     AS mri,
                pii.item_code                 AS item_code,
                pii.rate                      AS rate,
                pii.qty                       AS qty,
                pii.amount                    AS amount,
                pii.parent                    AS pinv,
                pi.supplier                   AS supplier
            FROM `tabPurchase Invoice Item` pii
            INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            WHERE pii.material_request IN %(mrs)s
              AND pi.docstatus = 1
        """, {"mrs": tuple(mr_names)}, as_dict=True)

        for r in pi_rows:
            key = r.mri or (r.mr, r.item_code)
            purchase.setdefault(key, []).append(r)

    # --- 5b. Expense Claim path ------------------------------------------------
    # Engineers sometimes buy materials with personal cash and reimburse via
    # Expense Claim. The standard Expense Claim Detail doctype has no native
    # link to Material Request, so this requires a custom field
    # `custom_material_request_item` on tabExpense Claim Detail.
    #
    # TODO[fields]: rename if your custom field uses a different fieldname.
    expense = {}  # key: mri name → list of {"exp", "supplier", "rate", "amount"}
    if mr_names:
        try:
            ec_rows = frappe.db.sql("""
                SELECT
                    ecd.custom_material_request_item AS mri,
                    ecd.description                  AS supplier_text,
                    ecd.amount                       AS amount,
                    ec.name                          AS exp,
                    ec.posting_date                  AS posting_date
                FROM `tabExpense Claim Detail` ecd
                INNER JOIN `tabExpense Claim` ec ON ec.name = ecd.parent
                WHERE ecd.custom_material_request_item IN %(mris)s
                  AND ec.docstatus = 1
            """, {"mris": tuple(i.name for i in items) or ("__none__",)}, as_dict=True)
        except Exception:
            # Custom field not yet created → skip the EXP path silently.
            ec_rows = []

        for r in ec_rows:
            expense.setdefault(r.mri, []).append(r)

    # --- 6. Sales Invoice linkage ----------------------------------------------
    # TODO[fields]: This assumes Sales Invoice Item carries either:
    #   (a) a custom `material_request` reference back to the MREQ, OR
    #   (b) a custom `material_request_item` reference back to the MR row.
    # Adjust the WHERE clause to match your actual link.
    sinv_lookup = {}  # key: mri or (mr, item_code) → {"sinv", "month"}
    if mr_names:
        try:
            si_rows = frappe.db.sql("""
                SELECT
                    sii.material_request          AS mr,
                    sii.material_request_item     AS mri,
                    sii.item_code                 AS item_code,
                    sii.parent                    AS sinv,
                    si.posting_date               AS posting_date
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE sii.material_request IN %(mrs)s
                  AND si.docstatus = 1
            """, {"mrs": tuple(mr_names)}, as_dict=True)
        except Exception:
            # If the `material_request` field doesn't exist on Sales Invoice
            # Item, fall back to no SINV linkage rather than crashing.
            si_rows = []

        for r in si_rows:
            key = r.mri or (r.mr, r.item_code)
            sinv_lookup[key] = {
                "sinv": r.sinv,
                "month": formatdate(r.posting_date, "MMM yyyy") if r.posting_date else "",
            }

    # --- 7. Stitch everything together ------------------------------------------
    rows = []
    for idx, item in enumerate(items, start=1):
        mr = mr_by_name[item.parent]

        scope = (item.get("custom_scope")
                 or item_groups.get(item.item_code)
                 or "")

        # Optional client-side scope filter
        if filters.get("scope") and scope and scope.lower() != filters.scope.lower():
            continue

        key = item.name
        fallback_key = (item.parent, item.item_code)

        delivered_entry = delivered.get(key) or delivered.get(fallback_key) or {}
        qty_delivered = flt(delivered_entry.get("qty"))
        dnotes = delivered_entry.get("dnotes", [])

        purchase_rows = purchase.get(key) or purchase.get(fallback_key) or []
        expense_rows = expense.get(key) or []

        # Procurement path resolution. Either (or both) may be present;
        # cost prefers PINV when both exist (formal supplier invoice wins).
        if purchase_rows:
            unit_cost = flt(purchase_rows[0].rate)
            pinv_amount = sum(flt(p.amount) for p in purchase_rows)
            pinv = purchase_rows[0].pinv if len(purchase_rows) == 1 \
                   else _join_unique([p.pinv for p in purchase_rows])
            supplier = purchase_rows[0].supplier if len(purchase_rows) == 1 \
                       else _join_unique([p.supplier for p in purchase_rows])
        else:
            unit_cost = 0.0
            pinv_amount = 0.0
            pinv = ""
            supplier = ""

        if expense_rows:
            exp = expense_rows[0].exp if len(expense_rows) == 1 \
                  else _join_unique([e.exp for e in expense_rows])
            exp_amount = sum(flt(e.amount) for e in expense_rows)
            # If only EXP path was used, derive unit_cost / supplier from it
            if not purchase_rows:
                ordered = flt(item.qty) or 1.0
                unit_cost = exp_amount / ordered
                supplier = expense_rows[0].supplier_text or ""
        else:
            exp = ""
            exp_amount = 0.0

        amount = pinv_amount + exp_amount

        sinv_entry = sinv_lookup.get(key) or sinv_lookup.get(fallback_key) or {}

        # Optional unbilled-only filter
        if filters.get("show_unbilled_only") and sinv_entry.get("sinv"):
            continue

        rows.append({
            "row_type":          "detail",
            "no":                str(idx),
            "description":       item.item_name or item.description or "",
            "part_no":           item.get("custom_part_no") or item.item_code or "",
            "scope":             scope,
            "delivery_location": item.warehouse or mr.set_warehouse or "",
            "hq_or_zone":        mr.get("custom_hq_or_zone") or "",
            "date":              mr.transaction_date,
            "req":               item.parent,
            "qty_ordered":       flt(item.qty),
            "qty_delivered":     qty_delivered,
            "balance":           flt(item.qty) - qty_delivered,
            "uom":               item.uom,
            "dnote":             dnotes[0] if len(dnotes) == 1 else _join_unique(dnotes),
            "pinv":              pinv,
            "exp":               exp,
            "unit_cost":         unit_cost,
            "amount":            amount,
            "supplier":          supplier,
            "sinv":              sinv_entry.get("sinv", ""),
            "invoice_month":     sinv_entry.get("month", ""),
            # internal sort keys, dropped before render
            "_scope_key":        scope or "Uncategorised",
            "_mreq":             item.parent,
        })

    return rows


def _join_unique(values):
    seen = []
    for v in values:
        if v and v not in seen:
            seen.append(v)
    return ", ".join(seen)


# ════════════════════════════════════════════════════════════════════════════
#   GROUPING + SUBTOTALS
# ════════════════════════════════════════════════════════════════════════════

def _build_grouped_rows(raw_rows, filters):
    """
    Inserts section headers, scope subtotals, materials subtotal, VAT and
    Grand Total. Mirrors the row_type vocabulary used in the .js formatter.
    """
    if not raw_rows:
        return [{
            "row_type": "section_header",
            "description": _("No Material Requests found in this period."),
        }]

    # Group by scope, preserving SCOPE_ORDER, with leftovers at the end
    by_scope = {}
    for r in raw_rows:
        by_scope.setdefault(r["_scope_key"], []).append(r)

    ordered_scopes = [s for s in SCOPE_ORDER if s in by_scope] + \
                     [s for s in by_scope if s not in SCOPE_ORDER]

    output = []
    output.append({
        "row_type": "section_header",
        "description": _("── MATERIALS BY SCOPE ──"),
    })

    grand_subtotal = 0.0

    for scope in ordered_scopes:
        scope_rows = by_scope[scope]
        scope_total = sum(flt(r["amount"]) for r in scope_rows)
        grand_subtotal += scope_total

        output.append({
            "row_type": "scope_header",
            "description": scope,
        })

        for r in scope_rows:
            # Strip internal keys before adding to output
            r.pop("_scope_key", None)
            r.pop("_mreq", None)
            output.append(r)

        output.append({
            "row_type": "subtotal_scope",
            "description": _("Sub Total — {0}").format(scope),
            "amount": scope_total,
        })

    # Materials grand subtotal
    output.append({
        "row_type": "subtotal_materials",
        "description": _("SUBTOTAL — ALL MATERIALS"),
        "amount": grand_subtotal,
    })

    vat_amount = grand_subtotal * VAT_RATE
    output.append({
        "row_type": "vat_18%",
        "description": _("VAT @ 18%"),
        "amount": vat_amount,
    })

    output.append({
        "row_type": "grand_total",
        "description": _("GRAND TOTAL"),
        "amount": grand_subtotal + vat_amount,
    })

    return output


# ════════════════════════════════════════════════════════════════════════════
#   ACTION: CREATE SALES INVOICE
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def create_sales_invoice(filters):
    """
    Build a draft Sales Invoice for NMB Bank from the report's current period.
    One line per Material Request Item that has a Purchase Invoice but no
    existing Sales Invoice yet.
    """
    import json as _json
    if isinstance(filters, str):
        filters = _json.loads(filters)
    filters = frappe._dict(filters)
    _validate_filters(filters)

    raw_rows = _fetch_material_request_lines(filters)
    billable = [r for r in raw_rows if not r.get("sinv") and flt(r.get("amount")) > 0]

    if not billable:
        frappe.throw(_("No unbilled material lines found for this period."))

    # Billing rule: SINV rate = actual procurement cost × (1 + markup%).
    # Markup comes from the report filter; default 0 = bill at cost.
    markup = flt(filters.get("markup_percent")) / 100.0

    # TODO: confirm NMB Bank's Customer record name in your ERPNext
    customer = frappe.db.get_value(
        "Customer",
        {"customer_name": ["like", "%NMB%"]},
        "name",
    ) or "NMB Bank PLC"

    si = frappe.new_doc("Sales Invoice")
    si.customer = customer
    si.project = filters.project
    si.posting_date = filters.to_date
    si.due_date = filters.to_date

    for r in billable:
        cost_rate = flt(r["unit_cost"])
        billed_rate = cost_rate * (1.0 + markup)
        si.append("items", {
            "item_code":            None,  # falls back to item_name if no item_code
            "item_name":            r["description"],
            "description":          (
                "{desc}  |  cost {cost:,.0f} +{mk:.0f}% → {billed:,.0f}"
                .format(
                    desc=r["description"],
                    cost=cost_rate,
                    mk=markup * 100,
                    billed=billed_rate,
                )
            ),
            "qty":                  flt(r["qty_delivered"]) or flt(r["qty_ordered"]),
            "uom":                  r["uom"],
            "rate":                 billed_rate,
            "material_request":     r["req"],
        })

    si.set_missing_values()
    si.insert(ignore_permissions=False)
    return si.name
