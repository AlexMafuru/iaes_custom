"""
NMB HQ Monthly Billing — Quotation Generation
==============================================

Whitelisted Python action triggered by the "Generate Quotation" button on the
NMB HQ Monthly Billing report.

For each MREQ Item line passed in, creates one line on a draft Quotation
to NMB. One QTN per project per call. Saves as docstatus=0 — accountant
must review and submit manually.

PLACEMENT (must live in the same report folder):
    /apps/<your_app>/<your_app>/<module>/report/nmb_hq_monthly_billing/
        generate_quotation.py
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, add_months, formatdate


# ---------------------------------------------------------------------------
# Configuration — patch if assumptions are wrong
# ---------------------------------------------------------------------------
DEFAULT_VALIDITY_MONTHS = 1   # QTN validity from posting date
DEFAULT_QUOTATION_TO = "Customer"


@frappe.whitelist()
def generate(project, from_date, to_date, mreq_item_names):
    """Generate one draft Quotation containing the listed MREQ Item lines."""
    if isinstance(mreq_item_names, str):
        # Frappe sometimes passes JSON
        import json
        mreq_item_names = json.loads(mreq_item_names)

    if not mreq_item_names:
        frappe.throw(_("No MREQ Item lines passed."))

    customer = _resolve_customer(project)
    lines = _fetch_lines_for_qtn(mreq_item_names, project)

    if not lines:
        frappe.throw(_("None of the selected lines are eligible for quotation."))

    qtn = _build_quotation(customer, project, from_date, to_date, lines)
    qtn.insert(ignore_permissions=False)

    # Back-reference: tag each MREQ Item with the QTN
    _tag_mreq_items_with_qtn(lines, qtn.name)

    frappe.db.commit()

    return {
        "quotation": qtn.name,
        "lines_count": len(qtn.items),
        "grand_total": qtn.grand_total,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_customer(project):
    """Get the customer linked to the project. Falls back to a fixed value
    if no customer is linked."""
    customer = frappe.db.get_value("Project", project, "customer")
    if not customer:
        # Fallback for legacy projects with no linked customer
        customer = frappe.db.get_value(
            "Customer",
            {"customer_name": ["like", "%NMB%"]},
            "name"
        )
    if not customer:
        frappe.throw(
            _("Could not resolve customer for project {0}. "
              "Set the Customer field on the Project, or create a Customer matching NMB.").format(project)
        )
    return customer


def _fetch_lines_for_qtn(mreq_item_names, project):
    """Read each MREQ Item with its persisted pricing values."""
    rows = frappe.db.sql("""
        SELECT
            mri.name                            AS mreq_item_name,
            mri.parent                          AS mreq,
            mri.item_code                       AS item_code,
            mri.item_name                       AS item_name,
            mri.description                     AS description,
            mri.qty                             AS qty,
            mri.uom                             AS uom,
            mri.custom_final_price              AS final_price,
            mri.custom_quoted_in_qtn            AS already_quoted,
            mr.custom_approved_requisition_no   AS approved_requisition_no
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        WHERE mri.name IN %(names)s
          AND mr.docstatus = 1
          AND COALESCE(mri.project, mr.project) = %(project)s
    """, {"names": mreq_item_names, "project": project}, as_dict=True)

    eligible = []
    skipped_already_quoted = []
    skipped_no_price = []

    for r in rows:
        if r.already_quoted:
            skipped_already_quoted.append(r.mreq_item_name)
            continue
        if not r.final_price or flt(r.final_price) <= 0:
            skipped_no_price.append(r.mreq_item_name)
            continue
        eligible.append(r)

    if skipped_already_quoted:
        frappe.msgprint(
            _("Skipped {0} lines already on a Quotation.").format(len(skipped_already_quoted)),
            alert=True
        )
    if skipped_no_price:
        frappe.msgprint(
            _("Skipped {0} lines with no Final Price set.").format(len(skipped_no_price)),
            alert=True
        )

    return eligible


def _build_quotation(customer, project, from_date, to_date, lines):
    """Construct a draft Quotation document."""
    qtn = frappe.new_doc("Quotation")
    qtn.quotation_to = DEFAULT_QUOTATION_TO
    qtn.party_name = customer
    qtn.customer = customer
    qtn.transaction_date = today()
    qtn.valid_till = add_months(today(), DEFAULT_VALIDITY_MONTHS)
    qtn.project = project
    qtn.currency = "TZS"

    # Title for human readability
    period_label = _period_label(from_date, to_date)
    qtn.title = f"NMB HQ Billing – {period_label}"

    for line in lines:
        qtn.append("items", {
            "item_code": line.item_code,
            "item_name": line.item_name,
            "description": line.description or line.item_name,
            "qty": flt(line.qty),
            "uom": line.uom,
            "rate": flt(line.final_price),
            "project": project,
            "custom_approved_requisition_no": line.approved_requisition_no or "",
            "custom_source_mreq_item": f"{line.mreq} / {line.mreq_item_name}",
        })

    qtn.set_missing_values()
    return qtn


def _tag_mreq_items_with_qtn(lines, qtn_name):
    """Set custom_quoted_in_qtn on each MREQ Item we just included."""
    for line in lines:
        frappe.db.set_value(
            "Material Request Item",
            line.mreq_item_name,
            "custom_quoted_in_qtn",
            qtn_name,
            update_modified=False,
        )


def _period_label(from_date, to_date):
    f = getdate(from_date)
    t = getdate(to_date)
    if f.month == t.month and f.year == t.year:
        return formatdate(from_date, "MMMM YYYY")
    return f"{formatdate(from_date, 'd MMM')} – {formatdate(to_date, 'd MMM YYYY')}"


# ---------------------------------------------------------------------------
# Optional: untag a Quotation (rollback helper)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def untag_quotation(qtn_name):
    """Clear custom_quoted_in_qtn on every MREQ Item that was tagged
    with this QTN. Used when a draft Quotation is cancelled or deleted."""
    rows = frappe.get_all(
        "Material Request Item",
        filters={"custom_quoted_in_qtn": qtn_name},
        fields=["name"],
    )
    for r in rows:
        frappe.db.set_value(
            "Material Request Item",
            r.name,
            "custom_quoted_in_qtn",
            None,
            update_modified=False,
        )
    frappe.db.commit()
    return {"untagged": len(rows)}
