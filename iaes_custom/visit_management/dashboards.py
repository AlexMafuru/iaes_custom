# Copyright (c) 2026, Sales Team Strategy and contributors
"""Adds a Visits section to the Customer and Lead form dashboards (B4.4)."""

from frappe import _

# Customer Visit points at Customer/Lead through the Dynamic Link `party`,
# not through a field named after the doctype, so it must be declared here.
NON_STANDARD = {"Customer Visit": "party"}


def get_customer_dashboard_data(data=None):
    return _extend(data)


def get_lead_dashboard_data(data=None):
    return _extend(data)


def _extend(data):
    data = data or {}
    data.setdefault("transactions", [])
    data.setdefault("non_standard_fieldnames", {})
    data["non_standard_fieldnames"].update(NON_STANDARD)
    data["transactions"].append({
        "label": _("Visits"),
        "items": ["Customer Visit"],
    })
    return data
