"""Visit Management module: dashboard cards, charts and default settings.

Runs (idempotently) on every migrate and on fresh installs:

- Visit Management Settings defaults (2 visits/week, 180-day neglect
  threshold, per checklist B2.6 / B2.7)
- Number Cards: Open Visits, Overdue Visits, Visits Closed This Month,
  Follow-ups Overdue
- Dashboard Charts: Visits by Status, Visits by Sales Person, Visits
  Over Time
- Attaches the cards and charts to the Visit Management workspace

This is an after_migrate hook rather than a patch on purpose: Frappe
marks all patches as completed WITHOUT running them when an app is
freshly installed on a new site, so a patch would silently skip there.
An idempotent after_migrate hook covers both paths, and also restores
the workspace card links if a future workspace re-sync resets them.
"""

import json

import frappe

MODULE = "Visit Management"
WORKSPACE = "Visit Management"

NUMBER_CARDS = [
    {
        "name": "Open Visits",
        "filters": [
            ["Customer Visit", "status", "in", ["Open", "In Progress"], False],
        ],
        "color": "#2E5C8A",
    },
    {
        "name": "Overdue Visits",
        # Uses the stored is_overdue flag (maintained by validate + the daily
        # scheduled job) - number cards cannot parse "Today" as a date value.
        "filters": [
            ["Customer Visit", "is_overdue", "=", 1, False],
        ],
        "color": "#C0392B",
    },
    {
        "name": "Visits Closed This Month",
        "filters": [
            ["Customer Visit", "status", "=", "Closed", False],
            ["Customer Visit", "closed_on", "Timespan", "this month", False],
        ],
        "color": "#1E8449",
    },
    {
        "name": "Follow-ups Overdue",
        "filters": [
            ["Customer Visit", "follow_up_required", "=", 1, False],
        ],
        # Date comparison against today must be a dynamic filter - the desk
        # evaluates the expression at render time.
        "dynamic_filters": [
            ["Customer Visit", "follow_up_date", "<", "frappe.datetime.get_today()", False],
        ],
        "color": "#D68910",
    },
]

CHARTS = [
    {
        "name": "Visits by Status",
        "chart_type": "Group By",
        "group_by_type": "Count",
        "group_by_based_on": "status",
        "type": "Donut",
    },
    {
        "name": "Visits by Sales Person",
        "chart_type": "Group By",
        "group_by_type": "Count",
        "group_by_based_on": "assigned_to",
        "type": "Bar",
    },
    {
        "name": "Visits Over Time",
        "chart_type": "Count",
        "based_on": "visit_date",
        "type": "Line",
        "timespan": "Last Quarter",
        "time_interval": "Weekly",
    },
]


def ensure_settings():
    if not frappe.db.exists("DocType", "Visit Management Settings"):
        return
    settings = frappe.get_single("Visit Management Settings")
    changed = False
    if not settings.default_visits_per_week:
        settings.default_visits_per_week = 2
        changed = True
    if not settings.neglected_customer_days:
        settings.neglected_customer_days = 180
        changed = True
    if changed:
        settings.flags.ignore_permissions = True
        settings.save()


def ensure_number_cards():
    for card in NUMBER_CARDS:
        filters_json = json.dumps(card["filters"])
        dynamic_filters_json = json.dumps(card.get("dynamic_filters") or [])

        if frappe.db.exists("Number Card", card["name"]):
            # Self-heal filter drift on existing cards (idempotent).
            frappe.db.set_value("Number Card", card["name"], {
                "filters_json": filters_json,
                "dynamic_filters_json": dynamic_filters_json,
            }, update_modified=False)
            continue

        frappe.get_doc({
            "doctype": "Number Card",
            "name": card["name"],
            "label": card["name"],
            "type": "Document Type",
            "document_type": "Customer Visit",
            "function": "Count",
            "filters_json": filters_json,
            "dynamic_filters_json": dynamic_filters_json,
            "color": card["color"],
            "is_public": 1,
            "show_percentage_change": 0,
            "module": MODULE,
        }).insert(ignore_permissions=True)


def ensure_charts():
    for chart in CHARTS:
        if frappe.db.exists("Dashboard Chart", chart["name"]):
            continue
        doc = frappe.new_doc("Dashboard Chart")
        doc.chart_name = chart["name"]
        doc.chart_type = chart["chart_type"]
        doc.document_type = "Customer Visit"
        doc.type = chart["type"]
        doc.is_public = 1
        doc.module = MODULE
        doc.filters_json = "[]"
        for key in ("group_by_type", "group_by_based_on", "based_on",
                    "timespan", "time_interval"):
            if chart.get(key):
                setattr(doc, key, chart[key])
        doc.insert(ignore_permissions=True)


def ensure_workspace_links():
    if not frappe.db.exists("Workspace", WORKSPACE):
        return
    ws = frappe.get_doc("Workspace", WORKSPACE)
    existing_cards = {r.number_card_name for r in ws.number_cards}
    existing_charts = {r.chart_name for r in ws.charts}
    dirty = False

    for card in NUMBER_CARDS:
        if card["name"] not in existing_cards and frappe.db.exists(
                "Number Card", card["name"]):
            ws.append("number_cards",
                      {"number_card_name": card["name"], "label": card["name"]})
            dirty = True

    for chart in CHARTS:
        if chart["name"] not in existing_charts and frappe.db.exists(
                "Dashboard Chart", chart["name"]):
            ws.append("charts", {"chart_name": chart["name"], "label": chart["name"]})
            dirty = True

    if dirty:
        ws.flags.ignore_permissions = True
        ws.save()


def ensure_visit_dashboards():
    ensure_settings()
    ensure_number_cards()
    ensure_charts()
    ensure_workspace_links()


def after_install():
    ensure_visit_dashboards()


def after_migrate():
    ensure_visit_dashboards()
