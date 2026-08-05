import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class VisitTarget(Document):
    def validate(self):
        duplicate = frappe.db.exists("Visit Target", {
            "sales_person": self.sales_person,
            "effective_from": self.effective_from,
            "name": ["!=", self.name],
        })
        if duplicate:
            frappe.throw(
                _("A target for {0} effective {1} already exists ({2}).").format(
                    self.sales_person, self.effective_from, duplicate))
        if self.visits_per_week < 0:
            frappe.throw(_("Target visits per week cannot be negative."))


def get_weekly_target(sales_person, on_date=None):
    """Most recent active target on or before the given date."""
    on_date = getdate(on_date or nowdate())
    row = frappe.get_all(
        "Visit Target",
        filters={
            "sales_person": sales_person,
            "is_active": 1,
            "effective_from": ["<=", on_date],
        },
        fields=["visits_per_week"],
        order_by="effective_from desc",
        limit=1,
    )
    if row:
        return row[0].visits_per_week
    return frappe.db.get_single_value(
        "Visit Management Settings", "default_visits_per_week") or 0
