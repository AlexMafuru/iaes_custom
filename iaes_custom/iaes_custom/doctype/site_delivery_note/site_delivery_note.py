# -*- coding: utf-8 -*-
# Copyright (c) 2026, IAES and contributors
# License: MIT
#
# Site Delivery Note (SDN)
# ─────────────────────────────────────────────────────────────────────────────
# Lightweight operational document recording physical delivery of materials
# to the client site, BEFORE the formal PREC/QTN/SO/DN/SINV chain runs.
#
# Purpose:
#   • Captures the moment goods physically arrive at the customer's premises
#   • Bridges procurement (PO/PINV/PE, STE, Expense Claim) to billing
#     (QTN→SO→DN→SINV)
#   • No GL impact. No stock movement. Pure record-keeping.
#
# Architectural notes:
#   • Submittable (Draft → Submitted → Cancelled) so it has audit weight
#   • Items are pulled from existing source documents via the
#     get_pullable_lines() helper — this prevents the same physical delivery
#     from being recorded twice
#   • PREC creation is OPTIONAL and OPT-IN per SDN (button on form) —
#     not every SDN warrants a separate PREC (e.g. STE-sourced items already
#     have stock entries)
#   • Quotation creation is delegated to the NMB billing report workflow,
#     not this doctype — but this doctype tracks the "quoted" status

from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


# ════════════════════════════════════════════════════════════════════════════
#   DOCUMENT CONTROLLER
# ════════════════════════════════════════════════════════════════════════════

class SiteDeliveryNote(Document):

    def validate(self):
        self._validate_items_unique()
        self._compute_amounts()
        self._set_default_cost_center_from_project()

    def before_submit(self):
        if not self.items:
            frappe.throw(_("Cannot submit a Site Delivery Note with no items."))
        self.status = "Submitted"

    def on_submit(self):
        # No GL hooks. No stock hooks. Just status bookkeeping.
        pass

    def on_cancel(self):
        # If any line has been pulled into a PREC or Quotation, refuse to
        # cancel — those downstream documents must be cancelled first.
        bound = [r for r in self.items
                 if r.prec_created or r.quoted or r.invoiced]
        if bound:
            frappe.throw(_(
                "Cannot cancel — {0} line(s) are already linked to a "
                "Purchase Receipt, Quotation, or Sales Invoice. Cancel "
                "downstream documents first."
            ).format(len(bound)))
        self.status = "Cancelled"

    # ── validation helpers ──────────────────────────────────────────────────

    def _validate_items_unique(self):
        """
        Prevent the same source-document line from being recorded in two
        rows of this SDN. (Cross-SDN uniqueness is enforced via the
        get_pullable_lines() helper.)
        """
        seen = set()
        for r in self.items:
            if not r.source_doctype or not r.source_document or not r.source_row_name:
                continue
            key = (r.source_doctype, r.source_document, r.source_row_name)
            if key in seen:
                frappe.throw(_(
                    "Duplicate source line: {0} {1} row {2}"
                ).format(r.source_doctype, r.source_document, r.source_row_name))
            seen.add(key)

    def _compute_amounts(self):
        for r in self.items:
            r.amount = flt(r.qty) * flt(r.unit_cost)

    def _set_default_cost_center_from_project(self):
        if self.cost_center or not self.project:
            return
        # If Project has a default cost center, inherit it
        default = frappe.db.get_value("Project", self.project, "cost_center")
        if default:
            self.cost_center = default


# ════════════════════════════════════════════════════════════════════════════
#   GET ITEMS FROM (whitelisted helpers called by client-side picker)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_pullable_lines(project, source_doctype, from_date=None, to_date=None):
    """
    Return a list of source-document lines available to be pulled into an
    SDN — i.e. lines that:
      • belong to the given project (directly or via linked MREQ)
      • are on submitted source documents
      • have NOT already been recorded in any submitted SDN

    Returns: list of dicts with the columns the SDN line needs.
    """
    if not project or not source_doctype:
        return []

    handler = _SOURCE_HANDLERS.get(source_doctype)
    if not handler:
        frappe.throw(_("Unsupported source doctype: {0}").format(source_doctype))

    return handler(project, from_date, to_date)


# ── Handler: Purchase Invoice ───────────────────────────────────────────────

def _pull_from_purchase_invoice(project, from_date, to_date):
    """
    PINV lines whose `material_request` ties back to an MREQ on this project,
    OR whose `project` field directly matches.
    """
    conditions = ["pi.docstatus = 1"]
    params = {"project": project}

    conditions.append("""(
        pii.project = %(project)s
        OR pii.material_request IN (
            SELECT name FROM `tabMaterial Request` WHERE project = %(project)s
        )
    )""")

    if from_date:
        conditions.append("pi.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("pi.posting_date <= %(to_date)s")
        params["to_date"] = to_date

    where = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            'Purchase Invoice'            AS source_doctype,
            pii.parent                    AS source_document,
            pii.name                      AS source_row_name,
            pii.material_request          AS material_request,
            pii.material_request_item     AS material_request_item,
            pii.item_code                 AS item_code,
            pii.item_name                 AS item_name,
            pii.description               AS description,
            pii.qty                       AS qty,
            pii.uom                       AS uom,
            pii.rate                      AS unit_cost,
            pii.amount                    AS amount,
            pi.posting_date               AS posting_date,
            pi.supplier                   AS supplier
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE {where}
        ORDER BY pi.posting_date DESC, pii.idx
    """, params, as_dict=True)

    return _filter_already_pulled(rows)


# ── Handler: Purchase Order ─────────────────────────────────────────────────

def _pull_from_purchase_order(project, from_date, to_date):
    """
    PO lines (less common as SDN source — PINV is preferred — but useful
    when goods physically arrive before the supplier's invoice is in).
    """
    conditions = ["po.docstatus = 1"]
    params = {"project": project}

    conditions.append("""(
        poi.project = %(project)s
        OR poi.material_request IN (
            SELECT name FROM `tabMaterial Request` WHERE project = %(project)s
        )
    )""")

    if from_date:
        conditions.append("po.transaction_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("po.transaction_date <= %(to_date)s")
        params["to_date"] = to_date

    where = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            'Purchase Order'              AS source_doctype,
            poi.parent                    AS source_document,
            poi.name                      AS source_row_name,
            poi.material_request          AS material_request,
            poi.material_request_item     AS material_request_item,
            poi.item_code                 AS item_code,
            poi.item_name                 AS item_name,
            poi.description               AS description,
            poi.qty                       AS qty,
            poi.uom                       AS uom,
            poi.rate                      AS unit_cost,
            poi.amount                    AS amount,
            po.transaction_date           AS posting_date,
            po.supplier                   AS supplier
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE {where}
        ORDER BY po.transaction_date DESC, poi.idx
    """, params, as_dict=True)

    return _filter_already_pulled(rows)


# ── Handler: Stock Entry ────────────────────────────────────────────────────

def _pull_from_stock_entry(project, from_date, to_date):
    """
    STE Detail lines on submitted STEs that reference this project.
    Stock Entry doesn't have a per-line MR link by default; we match on
    parent-level project.
    """
    conditions = [
        "ste.docstatus = 1",
        "ste.project = %(project)s",
    ]
    params = {"project": project}

    if from_date:
        conditions.append("ste.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("ste.posting_date <= %(to_date)s")
        params["to_date"] = to_date

    where = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            'Stock Entry'                 AS source_doctype,
            sed.parent                    AS source_document,
            sed.name                      AS source_row_name,
            NULL                          AS material_request,
            NULL                          AS material_request_item,
            sed.item_code                 AS item_code,
            sed.item_name                 AS item_name,
            sed.description               AS description,
            sed.qty                       AS qty,
            sed.uom                       AS uom,
            sed.basic_rate                AS unit_cost,
            sed.basic_amount              AS amount,
            ste.posting_date              AS posting_date,
            NULL                          AS supplier
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` ste ON ste.name = sed.parent
        WHERE {where}
        ORDER BY ste.posting_date DESC, sed.idx
    """, params, as_dict=True)

    return _filter_already_pulled(rows)


# ── Handler: Expense Claim ──────────────────────────────────────────────────

def _pull_from_expense_claim(project, from_date, to_date):
    """
    Expense Claim Detail lines linked to MREQ items on this project.
    Requires the custom field `custom_material_request_item` on
    Expense Claim Detail.

    Per policy (May 2026): EXP is being phased out in favour of PO discipline,
    but historical and emergency-purchase EXP records still need SDN coverage.
    """
    conditions = [
        "ec.docstatus = 1",
        "ec.project = %(project)s",
    ]
    params = {"project": project}

    if from_date:
        conditions.append("ec.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("ec.posting_date <= %(to_date)s")
        params["to_date"] = to_date

    where = " AND ".join(conditions)

    try:
        rows = frappe.db.sql(f"""
            SELECT
                'Expense Claim'               AS source_doctype,
                ecd.parent                    AS source_document,
                ecd.name                      AS source_row_name,
                NULL                          AS material_request,
                ecd.custom_material_request_item AS material_request_item,
                NULL                          AS item_code,
                ecd.description               AS item_name,
                ecd.description               AS description,
                1                             AS qty,
                NULL                          AS uom,
                ecd.amount                    AS unit_cost,
                ecd.amount                    AS amount,
                ec.posting_date               AS posting_date,
                NULL                          AS supplier
            FROM `tabExpense Claim Detail` ecd
            INNER JOIN `tabExpense Claim` ec ON ec.name = ecd.parent
            WHERE {where}
            ORDER BY ec.posting_date DESC, ecd.idx
        """, params, as_dict=True)
    except Exception:
        # If the custom field doesn't exist yet, return empty rather than crash
        return []

    return _filter_already_pulled(rows)


# ── Registry ────────────────────────────────────────────────────────────────

_SOURCE_HANDLERS = {
    "Purchase Invoice": _pull_from_purchase_invoice,
    "Purchase Order":   _pull_from_purchase_order,
    "Stock Entry":      _pull_from_stock_entry,
    "Expense Claim":    _pull_from_expense_claim,
}


# ── Cross-SDN dedup ─────────────────────────────────────────────────────────

def _filter_already_pulled(candidate_rows):
    """
    Remove rows whose (source_doctype, source_document, source_row_name) is
    already on a submitted (non-cancelled) Site Delivery Note.
    """
    if not candidate_rows:
        return []

    keys = [
        (r["source_doctype"], r["source_document"], r["source_row_name"])
        for r in candidate_rows
        if r.get("source_row_name")
    ]
    if not keys:
        return candidate_rows

    # Build a query to find already-pulled keys in one round-trip
    pulled = frappe.db.sql("""
        SELECT
            sdni.source_doctype,
            sdni.source_document,
            sdni.source_row_name
        FROM `tabSite Delivery Note Item` sdni
        INNER JOIN `tabSite Delivery Note` sdn ON sdn.name = sdni.parent
        WHERE sdn.docstatus = 1
          AND sdni.source_doctype IN %(doctypes)s
    """, {
        "doctypes": tuple({k[0] for k in keys}),
    }, as_dict=True)

    pulled_set = {
        (p["source_doctype"], p["source_document"], p["source_row_name"])
        for p in pulled
    }

    return [
        r for r in candidate_rows
        if (r["source_doctype"], r["source_document"], r["source_row_name"])
            not in pulled_set
    ]


# ════════════════════════════════════════════════════════════════════════════
#   DOWNSTREAM: PURCHASE RECEIPT CREATION
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def make_purchase_receipt_from_sdn(sdn_name, target_warehouse):
    """
    Create a Purchase Receipt from SDN lines that came from PO/PINV (i.e.
    the formal-procurement path). Lines from STE or Expense Claim are
    skipped because their stock recognition belongs to those doctypes.

    Groups lines by Purchase Order to honour ERPNext's one-PREC-per-PO rule
    where possible. If lines came from PINV (no PO), creates a separate
    no-PO PREC for those.
    """
    if not target_warehouse:
        frappe.throw(_("Target warehouse is required."))

    sdn = frappe.get_doc("Site Delivery Note", sdn_name)
    if sdn.docstatus != 1:
        frappe.throw(_("SDN must be Submitted before creating PREC."))

    eligible = [
        r for r in sdn.items
        if r.source_doctype in ("Purchase Order", "Purchase Invoice")
        and not r.prec_created
    ]
    if not eligible:
        frappe.throw(_(
            "No PREC-eligible lines on this SDN. Lines from Stock Entry "
            "or Expense Claim do not get a separate Purchase Receipt."
        ))

    # Group by underlying PO if possible
    by_po = {}
    no_po = []
    for r in eligible:
        po = _find_po_for_source(r)
        if po:
            by_po.setdefault(po, []).append(r)
        else:
            no_po.append(r)

    created_precs = []

    for po, lines in by_po.items():
        prec = _build_prec(sdn, target_warehouse, source_po=po)
        for sdn_line in lines:
            _append_prec_item(prec, sdn_line, po=po)
        prec.insert(ignore_permissions=False)
        prec.submit()
        created_precs.append(prec.name)
        for sdn_line in lines:
            frappe.db.set_value(
                "Site Delivery Note Item", sdn_line.name,
                {"prec_created": 1, "purchase_receipt": prec.name},
            )

    if no_po:
        prec = _build_prec(sdn, target_warehouse, source_po=None)
        for sdn_line in no_po:
            _append_prec_item(prec, sdn_line, po=None)
        prec.insert(ignore_permissions=False)
        prec.submit()
        created_precs.append(prec.name)
        for sdn_line in no_po:
            frappe.db.set_value(
                "Site Delivery Note Item", sdn_line.name,
                {"prec_created": 1, "purchase_receipt": prec.name},
            )

    return created_precs


def _find_po_for_source(sdn_line):
    """Trace SDN line back to its originating PO, if any."""
    if sdn_line.source_doctype == "Purchase Order":
        return sdn_line.source_document
    if sdn_line.source_doctype == "Purchase Invoice":
        po = frappe.db.get_value(
            "Purchase Invoice Item",
            sdn_line.source_row_name,
            "purchase_order",
        )
        return po
    return None


def _build_prec(sdn, target_warehouse, source_po):
    prec = frappe.new_doc("Purchase Receipt")
    prec.posting_date = sdn.delivery_date
    prec.project = sdn.project
    if sdn.cost_center:
        prec.cost_center = sdn.cost_center
    if source_po:
        prec.supplier = frappe.db.get_value("Purchase Order", source_po, "supplier")
    # custom field on PREC pointing back to this SDN (set via Customize Form
    # — see deployment notes)
    if frappe.get_meta("Purchase Receipt").has_field("custom_site_delivery_note"):
        prec.custom_site_delivery_note = sdn.name
    prec.set("items", [])
    return prec


def _append_prec_item(prec, sdn_line, po):
    item_row = {
        "item_code":          sdn_line.item_code,
        "item_name":          sdn_line.item_name,
        "description":        sdn_line.description,
        "qty":                flt(sdn_line.qty),
        "uom":                sdn_line.uom,
        "rate":               flt(sdn_line.unit_cost),
        "warehouse":          prec.get("set_warehouse"),
        "project":            prec.project,
    }
    if po:
        item_row["purchase_order"] = po
    prec.append("items", item_row)


# ════════════════════════════════════════════════════════════════════════════
#   STATUS HELPERS (for HTML fields on the form)
# ════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_downstream_status_html(sdn_name):
    """
    Return inline HTML summarising what's happened to this SDN's lines:
    how many have PRECs, how many are quoted, how many are invoiced.
    Called from the form's downstream_section HTML fields.
    """
    sdn = frappe.get_doc("Site Delivery Note", sdn_name)
    total = len(sdn.items)
    if not total:
        return {"prec_html": "", "qtn_html": ""}

    prec_count = sum(1 for r in sdn.items if r.prec_created)
    quoted_count = sum(1 for r in sdn.items if r.quoted)
    invoiced_count = sum(1 for r in sdn.items if r.invoiced)

    def bar(label, n, total, color):
        pct = round(100 * n / total) if total else 0
        return (
            f'<div style="margin:4px 0;">'
            f'<span style="display:inline-block;width:140px;font-weight:600;">{label}:</span>'
            f'<span style="display:inline-block;background:{color};color:#fff;'
            f'padding:2px 8px;border-radius:3px;min-width:60px;text-align:center;">'
            f'{n}/{total} ({pct}%)</span></div>'
        )

    prec_html = bar("Purchase Receipt", prec_count, total, "#1a3a6b")
    qtn_html = (
        bar("Quoted to NMB", quoted_count, total, "#5a4a8a")
        + bar("Invoiced (SINV)", invoiced_count, total, "#155724")
    )
    return {"prec_html": prec_html, "qtn_html": qtn_html}
