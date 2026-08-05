# Copyright (c) 2026, Sales Team Strategy and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, nowdate, cint

CLOSING_FIELDS = {
    "actual_visit_date": "Actual Visit Date",
    "visit_outcome": "Visit Outcome",
    "next_step": "Next Step",
    "closing_remarks": "Closing Remarks",
}


class CustomerVisit(Document):
    # ------------------------------------------------------------------ hooks
    def validate(self):
        self.set_party_details()
        self.set_contact_details()
        self.track_reschedule()
        self.validate_dates()
        self.validate_closing()
        self.validate_follow_up()
        self.set_reference_summaries()
        self.set_overdue_flag()

    def before_insert(self):
        self.original_planned_date = self.visit_date
        self.reschedule_count = 0

    def after_insert(self):
        self.assign_to_owner()

    def on_update(self):
        if self.has_value_changed("status") and self.status == "Closed":
            self.handle_closure()
        if self.has_value_changed("assigned_to") and not self.is_new():
            self.assign_to_owner()

    # ------------------------------------------------------------ party logic
    def set_party_details(self):
        """party_name and territory cannot use fetch_from because party is a
        Dynamic Link, so they are resolved here instead."""
        if not (self.party_type and self.party):
            return

        if self.party_type == "Customer":
            row = frappe.db.get_value(
                "Customer", self.party, ["customer_name", "territory"], as_dict=True
            )
            if row:
                self.party_name = row.customer_name
                self.territory = row.territory
        else:
            row = frappe.db.get_value(
                "Lead", self.party,
                ["lead_name", "company_name", "territory", "mobile_no", "email_id"],
                as_dict=True,
            )
            if row:
                self.party_name = row.company_name or row.lead_name
                self.territory = row.territory
                if not self.contact_person:
                    self.contact_mobile = row.mobile_no
                    self.contact_email = row.email_id

    def set_contact_details(self):
        if not self.contact_person:
            return
        row = frappe.db.get_value(
            "Contact", self.contact_person,
            ["name", "first_name", "last_name", "mobile_no", "phone", "email_id"],
            as_dict=True,
        )
        if not row:
            return
        self.contact_display = " ".join(filter(None, [row.first_name, row.last_name]))
        self.contact_mobile = row.mobile_no or row.phone
        self.contact_email = row.email_id

    # -------------------------------------------------------------- date logic
    def track_reschedule(self):
        """2.4 - the rep overwrites Visit Date freely. The original is kept
        silently so on-time reporting stays possible."""
        if self.is_new():
            return
        if not self.original_planned_date:
            self.original_planned_date = self.get_doc_before_save().visit_date
        if self.has_value_changed("visit_date"):
            self.reschedule_count = cint(self.reschedule_count) + 1

    def validate_dates(self):
        # Visiting earlier than planned is fine and is not flagged.
        if self.follow_up_date and self.visit_date:
            if getdate(self.follow_up_date) < getdate(self.visit_date):
                frappe.throw(_("Follow-up Date cannot be before the Visit Date."))

    # ----------------------------------------------------------- closing logic
    def validate_closing(self):
        if self.status != "Closed":
            return
        missing = [label for fn, label in CLOSING_FIELDS.items() if not self.get(fn)]
        if missing:
            frappe.throw(
                _("Cannot close this visit. Please complete: {0}").format(
                    ", ".join(frappe.bold(m) for m in missing)
                )
            )
        if not self.closed_by:
            self.closed_by = frappe.session.user
        if not self.closed_on:
            self.closed_on = now_datetime()

    def validate_follow_up(self):
        if self.follow_up_required and self.status == "Closed":
            if not (self.follow_up_type and self.follow_up_date):
                frappe.throw(_("Follow-up Type and Follow-up Date are required."))

    def set_reference_summaries(self):
        for row in self.visit_references:
            row.reference_summary = get_reference_summary(
                row.reference_type, row.reference_name
            )

    def set_overdue_flag(self):
        self.is_overdue = int(
            self.status == "Open"
            and bool(self.visit_date)
            and getdate(self.visit_date) < getdate(nowdate())
        )

    # ------------------------------------------------------------- automation
    def assign_to_owner(self):
        """5.5 - notify the assignee, and the manager as well."""
        user = get_user_for_sales_person(self.assigned_to)
        if not user:
            return

        existing = frappe.get_all(
            "ToDo",
            filters={
                "reference_type": self.doctype,
                "reference_name": self.name,
                "allocated_to": user,
                "status": "Open",
            },
            limit=1,
        )
        if existing:
            return

        from frappe.desk.form.assign_to import add

        try:
            add({
                "assign_to": [user],
                "doctype": self.doctype,
                "name": self.name,
                "description": _("Customer visit to {0} on {1}").format(
                    self.party_name or self.party, self.visit_date
                ),
                "date": self.visit_date,
                "notify": 1,
            })
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Visit assignment failed")

        settings = get_settings()
        if settings.notify_manager_on_assignment and settings.sales_manager:
            if settings.sales_manager != user:
                notify_user(
                    settings.sales_manager,
                    _("Visit assigned: {0}").format(self.party_name or self.party),
                    _("{0} has been assigned a visit to {1} on {2}.").format(
                        self.assigned_to, self.party_name or self.party, self.visit_date
                    ),
                    self,
                )

    def handle_closure(self):
        """Close the ToDo, then chain the follow-up (5.1 / 5.2 / 5.3)."""
        self.close_open_todos()

        if not self.follow_up_required or self.follow_up_reference:
            return

        if self.follow_up_type == "Site Visit":
            ref = self.create_follow_up_visit()
        else:
            ref = self.create_follow_up_todo()

        if ref:
            self.db_set("follow_up_reference_type", ref.doctype, update_modified=False)
            self.db_set("follow_up_reference", ref.name, update_modified=False)

        if get_settings().create_calendar_event:
            event = self.create_calendar_event()
            if event:
                self.db_set("calendar_event", event.name, update_modified=False)

    def close_open_todos(self):
        for name in frappe.get_all(
            "ToDo",
            filters={
                "reference_type": self.doctype,
                "reference_name": self.name,
                "status": "Open",
            },
            pluck="name",
        ):
            frappe.db.set_value("ToDo", name, "status", "Closed")

    def create_follow_up_visit(self):
        visit = frappe.new_doc("Customer Visit")
        visit.party_type = self.party_type
        visit.party = self.party
        visit.contact_person = self.contact_person
        visit.visit_date = self.follow_up_date
        visit.assigned_to = self.assigned_to
        visit.visit_purpose = self.visit_purpose
        visit.visit_objective = _("Follow-up from {0}: {1}").format(
            self.name, self.next_step or ""
        )[:140]
        visit.source_visit = self.name
        visit.status = "Open"
        for row in self.visit_references:
            visit.append("visit_references", {
                "reference_type": row.reference_type,
                "reference_name": row.reference_name,
            })
        visit.insert(ignore_permissions=True)
        return visit

    def create_follow_up_todo(self):
        user = get_user_for_sales_person(self.assigned_to)
        todo = frappe.new_doc("ToDo")
        todo.allocated_to = user
        todo.date = self.follow_up_date
        todo.priority = "Medium"
        todo.reference_type = self.doctype
        todo.reference_name = self.name
        todo.description = _("{0} for {1} - {2}").format(
            self.follow_up_type, self.party_name or self.party, self.next_step or ""
        )
        todo.insert(ignore_permissions=True)
        return todo

    def create_calendar_event(self):
        user = get_user_for_sales_person(self.assigned_to)
        if not user:
            return None
        event = frappe.new_doc("Event")
        event.subject = _("Follow-up: {0}").format(self.party_name or self.party)
        event.starts_on = f"{self.follow_up_date} 09:00:00"
        event.event_type = "Private"
        event.description = self.closing_remarks
        event.append("event_participants", {
            "reference_doctype": self.doctype,
            "reference_docname": self.name,
        })
        event.insert(ignore_permissions=True)
        frappe.share.add("Event", event.name, user, write=1, notify=0)
        return event


# ================================================================== helpers
def get_reference_summary(reference_type, reference_name):
    if not (reference_type and reference_name):
        return None
    try:
        if reference_type == "Quotation":
            row = frappe.db.get_value(
                "Quotation", reference_name,
                ["grand_total", "currency", "status", "valid_till"], as_dict=True)
            if row:
                return _("{0} {1} | {2} | valid till {3}").format(
                    row.currency, frappe.utils.fmt_money(row.grand_total),
                    row.status, row.valid_till or "-")
        elif reference_type == "Project":
            row = frappe.db.get_value(
                "Project", reference_name,
                ["status", "percent_complete", "expected_end_date"], as_dict=True)
            if row:
                return _("{0} | {1}% complete | ends {2}").format(
                    row.status, frappe.utils.flt(row.percent_complete, 1),
                    row.expected_end_date or "-")
        elif reference_type == "Opportunity":
            row = frappe.db.get_value(
                "Opportunity", reference_name,
                ["status", "opportunity_amount", "currency"], as_dict=True)
            if row:
                return _("{0} | {1} {2}").format(
                    row.status, row.currency,
                    frappe.utils.fmt_money(row.opportunity_amount))
        elif reference_type == "Lead":
            row = frappe.db.get_value(
                "Lead", reference_name, ["status", "lead_name"], as_dict=True)
            if row:
                return _("{0} | {1}").format(row.lead_name, row.status)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Visit reference summary failed")
    return None


def get_user_for_sales_person(sales_person):
    """Sales Person -> Employee -> User. Falls back to a matching User id."""
    if not sales_person:
        return None
    employee = frappe.db.get_value("Sales Person", sales_person, "employee")
    if employee:
        user = frappe.db.get_value("Employee", employee, "user_id")
        if user:
            return user
    return frappe.db.get_value("User", {"full_name": sales_person, "enabled": 1}, "name")


def get_settings():
    return frappe.get_cached_doc("Visit Management Settings")


def notify_user(user, subject, message, doc=None):
    notification = frappe.new_doc("Notification Log")
    notification.for_user = user
    notification.type = "Alert"
    notification.subject = subject
    notification.email_content = message
    if doc:
        notification.document_type = doc.doctype
        notification.document_name = doc.name
    notification.insert(ignore_permissions=True)


# =============================================================== whitelisted
@frappe.whitelist()
def close_visit(name, actual_visit_date, visit_outcome, next_step,
                closing_remarks, follow_up_required=0, follow_up_type=None,
                follow_up_date=None):
    """Called by the Close Visit dialog."""
    doc = frappe.get_doc("Customer Visit", name)
    doc.check_permission("write")
    doc.actual_visit_date = actual_visit_date
    doc.visit_outcome = visit_outcome
    doc.next_step = next_step
    doc.closing_remarks = closing_remarks
    doc.follow_up_required = cint(follow_up_required)
    doc.follow_up_type = follow_up_type
    doc.follow_up_date = follow_up_date
    doc.status = "Closed"
    doc.save()
    return doc.name


@frappe.whitelist()
def get_open_visit_count(party_type, party):
    return frappe.db.count("Customer Visit", {
        "party_type": party_type, "party": party,
        "status": ["in", ["Open", "In Progress"]],
    })
