"""
NMB Zone Monthly Billing Report  -  iaes_custom
================================================
Generates a billing-ready costing sheet for Project 74 (NMB Corrective
Electrical Services - Southern & Central Zones).

Billing model (per Award Letter, July 2023):
  - Service / Repair call   -> TZS 200,000 per task/visit
  - Power Audit             -> TZS 650,000 per task/visit
  - Spare parts / Materials -> Contract price list (qty x unit price)
                               OR purchase price + margin (if not on list)
  - Rewiring labour         -> 15% of materials used in overhaul tasks
  - Transport               -> 2% of material cost (only when cost > 5 M)
  - VAT                     -> 18%
"""

import frappe
from frappe import _
from frappe.utils import flt

# -- HTML stripper -----------------------------------------------------------
import re as _re

def _strip_html(text):
    if not text:
        return ""
    text = _re.sub(r'<[^>]+>', ' ', str(text))
    text = text.replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&nbsp;',' ').replace('&#39;',"'").replace('&quot;','"')
    return ' '.join(text.split())


# -- HTML stripper -----------------------------------------------------------
import re as _re



# -- Contract rates (Award Letter) -------------------------------------------
SERVICE_CALL_RATE   = 200_000
POWER_AUDIT_RATE    = 650_000
REWIRING_LABOUR_PCT = 0.15
TRANSPORT_PCT       = 0.02
TRANSPORT_THRESHOLD = 5_000_000
VAT_RATE            = 0.18

# -- Agreed spare-part prices (price schedule, VAT excl.) --------------------
# Lower-case item-name fragment -> unit price (TZS).
# Tip: move these to a Frappe Price List for easier maintenance.
CONTRACT_PRICE_MAP = {
    "led wall mount water proof":             34_220,
    "led down sport lights 24":               38_500,
    "led down sport lights 36":               25_000,
    "led flood lights 60w":                  103_500,
    "led flood lights 80w":                  178_000,
    "led flood lights 100w":                  53_040,
    "led flood lights 40w":                   37_016.80,
    "led flood lights 20w":                   14_700,
    "led flood lights 10w":                    9_800,
    "led panel lights 48":                    58_900,
    "led t8 lights":                          10_400,
    "led t5 lights":                           5_700,
    "led bulbs":                               4_832,
    "bulb":                                    8_750,
    "switch socket":                          12_500,
    "double pole switch 20a":                  6_060,
    "double pole switch 45a":                 12_202.80,
    "3 c x 2.5mm2 cu cable":                  5_491.20,
    "4 c x 16mm2 pvc cu cable":              26_040,
    "4 c x 16mm2":                           52_500,
    "flexible cable":                          4_800,
    "cable trunking (normal) 16mmx25mm":       6_200,
    "cable trunking (normal) 50mm":           10_500,
    "cable trunking three compartment 175mm": 96_100,
    "cable trunking two compartment 100mm":   44_100,
    "surface box":                             1_600,
    "extension cable":                        31_250,
    "extension reel":                        101_600,
    "top plug 13a":                            3_400,
    "top plug 15a":                            3_675,
    "1 pole, 20a":                            12_800,
    "1 pole, 16a":                             8_900,
    "1 pole, 10a":                             8_900,
    "2 way, 3-4gang":                          5_084.40,
    "change over breaker":                    76_800,
    "4 pole, 125a":                          210_512,
    "three phase, 12 way":                   414_237.60,
    "single phase, 12 way":                  141_355.20,
    "hdmi cable":                             31_250,
    "insulation tape":                         1_875,
    "pvc/metalic saddle":                        400,
    "cooker socket":                          43_750,
    "rccd 4 pole, 125a":                     138_900,
    "rccd 4 pole, 100a":                      91_900,
    "mcb 1 pole, 20a":                        12_800,
}


# -- Helpers ------------------------------------------------------------------

def _month_label(d):
    if not d:
        return ""
    try:
        return d.strftime("%B")
    except Exception:
        return ""


def get_contract_rate(item_name):
    """Return contract unit price for an item, or None if unlisted."""
    if not item_name:
        return None
    lower = item_name.lower()
    for key, price in CONTRACT_PRICE_MAP.items():
        if key in lower:
            return price
    return None


def _parse_subject(subject):
    """
    Tasks are named like: 'NMB WAMI - LIGHT REPLACEMENT'
    Returns (branch_name, fault_description).
    """
    parts = (subject or "").split(" - ", 1)
    branch = parts[0].strip()
    fault  = parts[1].strip() if len(parts) > 1 else ""
    return branch, fault


def _subtotal_row(label, amount, indent=""):
    return {
        "sno": "", "date": "", "month": "", "task": "",
        "branch_name": f"{indent}{label}",
        "fault_reported": "", "category": "", "unit": "",
        "qty": None, "rate": None, "amount": amount,
        "task_status": "", "zone": "",
        "assigned_to": "", "attachment": "",
        "row_type": label.lower().replace(" ", "_"),
    }


def _date_filter(field, from_date, to_date):
    """
    Build a safe Frappe date filter dict for a given field.
    Avoids the double-assignment bug where two separate if-blocks
    overwrite the same key.
    """
    if from_date and to_date:
        return {field: ["between", [from_date, to_date]]}
    if from_date:
        return {field: [">=", from_date]}
    if to_date:
        return {field: ["<=", to_date]}
    return {}



# -- Task metadata bulk fetcher -----------------------------------------------

def _get_task_meta_bulk(task_names):
    """
    Returns {task_name: {"assigned_to": "Full Name, ...", "attachment": "Yes (N)" or "None"}}
    for all tasks in task_names. Uses three DB queries total (no per-row hits).
    """
    if not task_names:
        return {}

    import json as _json

    # 1. Fetch _assign JSON from all tasks in one query
    task_rows = frappe.get_all(
        "Task",
        filters={"name": ["in", task_names]},
        fields=["name", "_assign"],
    )

    # 2. Collect all unique assignee emails across tasks
    assignee_emails = set()
    task_assignees  = {}
    for t in task_rows:
        try:
            emails = _json.loads(t._assign or "[]")
        except Exception:
            emails = []
        task_assignees[t.name] = emails
        assignee_emails.update(emails)

    # 3. Resolve emails -> full names in one query
    email_to_name = {}
    if assignee_emails:
        users = frappe.get_all(
            "User",
            filters={"name": ["in", list(assignee_emails)]},
            fields=["name", "full_name"],
        )
        email_to_name = {u.name: u.full_name or u.name for u in users}

    # 4. Count attachments per task in one query
    attachments = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Task",
            "attached_to_name":    ["in", task_names],
        },
        fields=["attached_to_name", "file_name"],
    )
    att_count = {}
    for att in attachments:
        att_count[att.attached_to_name] = att_count.get(att.attached_to_name, 0) + 1

    # 5. Build final result
    result = {}
    for task_name in task_names:
        emails = task_assignees.get(task_name, [])
        names  = [email_to_name.get(e, e) for e in emails]
        count  = att_count.get(task_name, 0)
        result[task_name] = {
            "assigned_to": ", ".join(names) if names else "Unassigned",
            "attachment":  "Yes ({})".format(count) if count else "None",
        }
    return result

# -- Main entry point ---------------------------------------------------------

def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    C = lambda label, fn, ft, w, **kw: {
        "label": _(label), "fieldname": fn, "fieldtype": ft, "width": w, **kw
    }
    return [
        C("S/No",           "sno",           "Int",      50),
        C("Date",           "date",          "Date",    100),
        C("Month",          "month",         "Data",     80),
        C("Task No",        "task",          "Link",    110, options="Task"),
        C("Branch Name",    "branch_name",   "Data",    230),
        C("Fault Reported", "fault_reported","Data",    220),
        C("Category",       "category",      "Data",    110),
        C("Unit",           "unit",          "Data",     55),
        C("QTY",            "qty",           "Float",    60),
        C("Rate (TZS)",     "rate",          "Currency",135),
        C("Amount (TZS)",   "amount",        "Currency",135),
        C("Task Status",    "task_status",   "Data",     90),
        C("Zone",           "zone",          "Data",     80),
        C("Assigned To",    "assigned_to",   "Data",    160),
        C("Attachment",     "attachment",    "Data",     95),
        C("row_type",       "row_type",      "Data",      0,   hidden=1),
    ]


# -- Data builder -------------------------------------------------------------

def get_data(filters):
    project     = filters.get("project")
    from_date   = filters.get("from_date")
    to_date     = filters.get("to_date")
    zone_filter = filters.get("zone")

    rows = []
    sno  = 0

    # -- SECTION 1: CALL-OUT / LABOUR CHARGES ---------------------------------
    rows.append({**_subtotal_row("-- SECTION 1: CALL OUT CHARGES --", None),
                 "row_type": "section_header"})

    task_filters = {"project": project}
    task_filters.update(_date_filter("exp_end_date", from_date, to_date))
    if zone_filter:
        task_filters["type"] = ["like", "%{}%".format(zone_filter)]

    tasks = frappe.get_all(
        "Task",
        filters=task_filters,
        fields=["name", "subject", "status", "type",
                "exp_end_date", "act_start_date"],
        order_by="exp_end_date asc, name asc",
    )

    # Bulk-fetch assignments + attachments for all tasks (3 queries total)
    task_meta = _get_task_meta_bulk([t.name for t in tasks])

    callout_total = 0.0
    for task in tasks:
        branch, fault = _parse_subject(task.subject)
        is_audit  = any(kw in (task.subject or "").lower()
                        for kw in ("power audit", "audit"))
        rate      = POWER_AUDIT_RATE if is_audit else SERVICE_CALL_RATE
        category  = "Power Audit"   if is_audit else "Service call"
        task_date = task.exp_end_date or task.act_start_date
        meta      = task_meta.get(task.name, {})
        sno += 1
        callout_total += rate
        rows.append({
            "sno": sno, "date": task_date, "month": _month_label(task_date),
            "task": task.name, "branch_name": branch, "fault_reported": fault,
            "category": category, "unit": "Item", "qty": 1, "rate": rate,
            "amount": rate, "task_status": task.status, "zone": task.type or "",
            "assigned_to": meta.get("assigned_to", ""),
            "attachment":  meta.get("attachment", ""),
            "row_type": "detail",
        })

    rows.append(_subtotal_row("Subtotal 1 - Call Out Charges", callout_total))

    # -- SECTION 2: SPARE PARTS / MATERIALS -----------------------------------
    rows.append({**_subtotal_row("-- SECTION 2: PARTS REPLACEMENTS --", None),
                 "row_type": "section_header"})

    exp_materials  = _get_expense_claim_materials(project, from_date, to_date, zone_filter)
    pinv_materials = _get_pinv_materials(project, from_date, to_date, zone_filter)

    # Group by task (or project if task unknown)
    by_task = {}
    for item in exp_materials + pinv_materials:
        key = item.get("task") or project
        by_task.setdefault(key, []).append(item)

    materials_total = 0.0
    for task_ref, items in by_task.items():
        branch_label = task_ref
        task_status  = ""
        task_zone    = ""
        if task_ref and task_ref.upper().startswith("TASK"):
            try:
                td = frappe.get_doc("Task", task_ref)
                branch_label, _ = _parse_subject(td.subject)
                task_status     = td.status
                task_zone       = td.type or ""
            except Exception:
                pass

        rows.append({**_subtotal_row(
            f"PARTS REPLACEMENT AT {branch_label} BRANCH", None),
            "row_type": "branch_header"})

        branch_total = 0.0
        for it in items:
            sno += 1
            branch_total    += flt(it["amount"])
            materials_total += flt(it["amount"])
            rows.append({
                "sno": sno, "date": it.get("date"), "month": it.get("month", ""),
                "task": task_ref if task_ref.upper().startswith("TASK") else "",
                "branch_name": _strip_html(it.get("item_name", it.get("description", ""))),
                "fault_reported": it.get("expense_type", it.get("item_group", "Materials")),
                "category": "materials", "unit": it.get("unit", "pcs"),
                "qty": flt(it.get("qty", 1)), "rate": flt(it.get("rate", 0)),
                "amount": flt(it["amount"]),
                "task_status": task_status, "zone": task_zone,
                "assigned_to": "", "attachment": "",
                "row_type": "detail",
            })

        rows.append(_subtotal_row(f"Sub Total - {branch_label}", branch_total, "    "))

    rows.append(_subtotal_row("Subtotal 2 - Parts Replacements", materials_total))

    # -- SECTION 3: REWIRING LABOUR (15% of overhaul materials) --------------
    rewiring_mat    = _get_rewiring_materials(project, from_date, to_date)
    rewiring_labour = flt(rewiring_mat) * REWIRING_LABOUR_PCT
    if rewiring_labour:
        sno += 1
        rows.append({
            "sno": sno, "date": None, "month": "",
            "task": "", "branch_name": "Rewiring Labour (15% of Rewiring Materials)",
            "fault_reported": "", "category": "Labour", "unit": "Item",
            "qty": 1, "rate": rewiring_labour, "amount": rewiring_labour,
            "task_status": "", "zone": "", "assigned_to": "", "attachment": "",
            "row_type": "detail",
        })

    # -- TRANSPORT (2% of materials, only when > 5 M) -----------------------
    transport = 0.0
    if materials_total > TRANSPORT_THRESHOLD:
        transport = materials_total * TRANSPORT_PCT
        sno += 1
        rows.append({
            "sno": sno, "date": None, "month": "",
            "task": "", "branch_name": "Material Transportation Cost (2% of materials)",
            "fault_reported": "", "category": "Transport", "unit": "Item",
            "qty": 1, "rate": transport, "amount": transport,
            "task_status": "", "zone": "", "assigned_to": "", "attachment": "",
            "row_type": "detail",
        })

    # -- TOTALS ---------------------------------------------------------------
    subtotal3   = callout_total + materials_total + rewiring_labour + transport
    vat         = subtotal3 * VAT_RATE
    grand_total = subtotal3 + vat

    rows.append(_subtotal_row("Subtotal 3",  subtotal3))
    rows.append(_subtotal_row("VAT 18%",     vat))
    rows.append(_subtotal_row("GRAND TOTAL", grand_total))

    return rows


# -- Data fetchers ------------------------------------------------------------

def _get_expense_claim_materials(project, from_date, to_date, zone_filter=None):
    """Expense Claim lines with expense_type = Material for this project."""
    # Zone filter: restrict to tasks in selected zone only
    allowed_tasks = None
    if zone_filter:
        allowed_tasks = set(frappe.get_all(
            "Task",
            filters={"project": project, "type": ["like", "%{}%".format(zone_filter)]},
            pluck="name",
        ))

    # Get all task names in this project
    project_tasks = frappe.get_all(
        "Task",
        filters={"project": project},
        pluck="name",
    )

    # Query 1: ECs linked directly to project
    ec_filters_proj = {"project": project, "docstatus": 1}
    ec_filters_proj.update(_date_filter("posting_date", from_date, to_date))

    # Query 2: ECs linked via task
    ec_filters_task = {"docstatus": 1}
    ec_filters_task.update(_date_filter("posting_date", from_date, to_date))
    if project_tasks:
        ec_filters_task["task"] = ["in", project_tasks]

    seen = set()
    claims = []
    for ec_filters in [ec_filters_proj, ec_filters_task]:
        rows = frappe.get_all(
            "Expense Claim",
            filters=ec_filters,
            fields=["name", "posting_date", "task", "project"],
        )
        for r in rows:
            if r.name not in seen:
                seen.add(r.name)
                claims.append(r)

    result = []
    for claim in claims:
        # Zone filter: skip ECs whose task is not in the allowed zone
        if allowed_tasks is not None:
            claim_task = claim.get("task") or ""
            if not claim_task:
                continue
            if claim_task not in allowed_tasks:
                continue

        details = frappe.get_all(
            "Expense Claim Detail",
            filters={"parent": claim.name},
            fields=["expense_type", "description", "amount", "sanctioned_amount"],
        )
        for d in details:
            if (d.expense_type or "").strip().lower() != "material":
                continue
            pd_           = claim.posting_date
            contract_rate = get_contract_rate(d.description)
            amt           = flt(d.sanctioned_amount or d.amount)
            result.append({
                "date": pd_, "month": _month_label(pd_),
                "task": claim.get("task") or "",
                "item_name": _strip_html(d.description),
                "expense_type": d.expense_type,
                "qty": 1, "unit": "Item",
                "rate": contract_rate or amt,
                "amount": amt,
                "source": "Expense Claim",
            })
    return result


def _get_pinv_materials(project, from_date, to_date, zone_filter=None):
    """
    Purchase Invoice items linked to the project.
    Uses per-line task field if the custom field exists,
    otherwise attributes the item to the header project.
    When zone_filter set, only includes items linked to tasks in that zone.
    """
    # Pre-fetch allowed tasks for zone filtering
    allowed_tasks = None
    if zone_filter:
        allowed_tasks = set(frappe.get_all(
            "Task",
            filters={"project": project, "type": ["like", "%{}%".format(zone_filter)]},
            pluck="name",
        ))
    inv_filters = {"project": project, "docstatus": 1}
    inv_filters.update(_date_filter("posting_date", from_date, to_date))

    invoices = frappe.get_all(
        "Purchase Invoice",
        filters=inv_filters,
        fields=["name", "posting_date", "project"],
    )

    has_task_field = frappe.db.exists(
        "Custom Field",
        {"dt": "Purchase Invoice Item", "fieldname": "task"}
    )
    extra_fields = ["task"] if has_task_field else []
    EXCLUDE_GROUPS = {
        "motor vehicle", "vehicle", "car hire", "transport vehicle",
        "food", "meals", "accommodation", "stationery", "office supplies",
    }

    result = []
    for inv in invoices:
        items = frappe.get_all(
            "Purchase Invoice Item",
            filters={"parent": inv.name},
            fields=["item_name", "item_code", "item_group", "qty", "uom",
                    "rate", "amount", "description"] + extra_fields,
        )
        for it in items:
            # Skip non-electrical items (car hire, food, etc.)
            if any(x in (it.item_group or '').lower() for x in EXCLUDE_GROUPS):
                continue
            # Skip zero-amount lines
            if not flt(it.amount):
                continue
            # Zone filter: skip items whose task is not in the allowed zone
            if allowed_tasks is not None:
                item_task = it.get("task") or inv.get("task") or ""
                if item_task and item_task not in allowed_tasks:
                    continue
                if not item_task:
                    continue  # no task link — cannot verify zone, skip
            pd_    = inv.posting_date
            c_rate = get_contract_rate(it.item_name or it.item_code or it.description)
            qty    = flt(it.qty) or 1
            rate   = c_rate if c_rate else flt(it.rate)
            # Use actual PINV amount to capture all items regardless of price map
            amt    = flt(it.amount)
            result.append({
                "date": pd_, "month": _month_label(pd_),
                "task": it.get("task") or "",
                "item_name": it.item_name or it.item_code,
                "item_group": it.item_group,
                "description": _strip_html(it.description or it.item_name or ""),
                "qty": qty, "unit": it.uom or "pcs",
                "rate": rate, "amount": amt,
                "source": "Purchase Invoice",
            })
    return result


def _get_rewiring_materials(project, from_date, to_date):
    """
    Sum material costs for tasks whose subject contains 'overhaul' or 'rewiring'.
    Used to derive the 15% rewiring labour charge.
    """
    overhaul_tasks = frappe.get_all(
        "Task",
        filters={"project": project, "subject": ["like", "%overhaul%"]},
        pluck="name",
    ) + frappe.get_all(
        "Task",
        filters={"project": project, "subject": ["like", "%rewiring%"]},
        pluck="name",
    )
    if not overhaul_tasks:
        return 0

    total = 0.0
    for task_name in set(overhaul_tasks):
        claims = frappe.get_all(
            "Expense Claim",
            filters={"task": task_name, "docstatus": 1},
            fields=["name"],
        )
        for claim in claims:
            lines = frappe.get_all(
                "Expense Claim Detail",
                filters={"parent": claim.name, "expense_type": "Materials"},
                fields=["sanctioned_amount", "amount"],
            )
            for line in lines:
                total += flt(line.sanctioned_amount or line.amount)
    return total


# -- One-click Sales Invoice creation -----------------------------------------

@frappe.whitelist()
def create_sales_invoice(filters):
    """
    Called from the JS 'Create Sales Invoice' button.
    Builds a draft Sales Invoice and returns its name.
    Adjust customer and income_account to match your Chart of Accounts.
    """
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)

    _, data = execute(filters)

    si              = frappe.new_doc("Sales Invoice")
    si.customer     = "NMB BANK PLC"   # <-- update to your ERPNext customer name
    si.project      = filters.get("project")
    si.due_date     = frappe.utils.add_days(frappe.utils.today(), 30)
    INCOME_ACCOUNT  = "Service - IAES"  # <-- update to your Chart of Accounts

    for row in data:
        if row.get("row_type") != "detail":
            continue
        if not flt(row.get("amount")):
            continue
        si.append("items", {
            "item_name":      _strip_html(row.get("branch_name", "Electrical Service")),
            "description":    "{} | {}".format(
                                  row.get("task", ""),
                                  _strip_html(row.get("fault_reported", ""))),
            "qty":            row.get("qty") or 1,
            "rate":           row.get("rate") or row.get("amount"),
            "income_account": INCOME_ACCOUNT,
        })

    si.insert(ignore_permissions=True)
    return si.name