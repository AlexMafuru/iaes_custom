import frappe
from frappe.model.document import Document


class VisitManagementSettings(Document):
    def on_update(self):
        frappe.clear_cache(doctype="Visit Management Settings")
