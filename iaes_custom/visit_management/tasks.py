# Copyright (c) 2026, Sales Team Strategy and contributors
"""Scheduled jobs.

Every function here is plain Python inside this app. Nothing depends on the
Server Script doctype, which is disabled on Frappe Cloud.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, add_days, get_link_to_form, flt


# ------------------------------------------------------------------ overdue
def flag_overdue_visits():
    """Keep the stored is_overdue flag in step with the derived state.

    The flag exists only so number cards and list filters stay fast. The
    reports never trust it - they derive Overdue from visit_date directly.
    """
    today = nowdate()

    frappe.db.sql(
        """
        UPDATE `tabCustomer Visit`
        SET is_overdue = 1
        WHERE status = 'Open' AND visit_date < %s AND is_overdue = 0
        """,
        today,
    )
    frappe.db.sql(
        """
        UPDATE `tabCustomer Visit`
        SET is_overdue = 0
        WHERE (status != 'Open' OR visit_date >= %s) AND is_overdue = 1
        """,
        today,
    )
    frappe.db.commit()


# ---------------------------------------------------------------- reminders
def send_visit_reminders():
    """Morning reminder to each assignee for visits due today."""
    from iaes_custom.visit_management.doctype.customer_visit.customer_visit import (
        get_user_for_sales_person,
    )

    visits = frappe.get_all(
        "Customer Visit",
        filters={"status": ["in", ["Open", "In Progress"]], "visit_date": nowdate()},
        fields=["name", "party_name", "party", "assigned_to", "visit_time",
                "visit_objective"],
    )
    if not visits:
        return

    by_person = {}
    for v in visits:
        by_person.setdefault(v.assigned_to, []).append(v)

    for sales_person, rows in by_person.items():
        user = get_user_for_sales_person(sales_person)
        if not user:
            continue
        lines = "".join(
            f"<li>{frappe.utils.escape_html(r.party_name or r.party)}"
            f"{' at ' + str(r.visit_time) if r.visit_time else ''} "
            f"&mdash; {get_link_to_form('Customer Visit', r.name)}</li>"
            for r in rows
        )
        _notify(
            user,
            _("You have {0} visit(s) today").format(len(rows)),
            f"<p>{_('Your visits scheduled for today')}:</p><ul>{lines}</ul>",
        )


# ------------------------------------------------------------------ digest
def send_overdue_digest():
    """B5.6 - daily overdue digest to the sales manager."""
    settings = frappe.get_cached_doc("Visit Management Settings")
    if not settings.send_overdue_digest or not settings.sales_manager:
        return

    rows = frappe.db.sql(
        """
        SELECT name, party_name, party, assigned_to, visit_date,
               DATEDIFF(CURDATE(), visit_date) AS days_overdue
        FROM `tabCustomer Visit`
        WHERE status = 'Open' AND visit_date < CURDATE()
        ORDER BY visit_date ASC
        """,
        as_dict=True,
    )
    if not rows:
        return

    body = [
        "<p>", _("The following visits are past their planned date."), "</p>",
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;font-family:sans-serif;font-size:13px'>",
        "<tr style='background:#1F3864;color:#fff'>",
        f"<th>{_('Visit')}</th><th>{_('Party')}</th><th>{_('Assigned To')}</th>",
        f"<th>{_('Planned')}</th><th>{_('Days Overdue')}</th></tr>",
    ]
    for r in rows:
        body.append(
            f"<tr><td>{get_link_to_form('Customer Visit', r.name)}</td>"
            f"<td>{frappe.utils.escape_html(r.party_name or r.party)}</td>"
            f"<td>{frappe.utils.escape_html(r.assigned_to or '')}</td>"
            f"<td>{r.visit_date}</td><td align='right'>{r.days_overdue}</td></tr>"
        )
    body.append("</table>")

    _email(
        settings.sales_manager,
        _("Overdue visits: {0}").format(len(rows)),
        "".join(body),
    )


def send_weekly_performance_digest():
    """B6.3 - weekly performance summary, Mondays at 08:00."""
    settings = frappe.get_cached_doc("Visit Management Settings")
    if not settings.send_weekly_performance_digest or not settings.sales_manager:
        return

    to_date = nowdate()
    from_date = add_days(to_date, -7)

    from iaes_custom.visit_management.report.sales_person_visit_performance import (
        sales_person_visit_performance as report,
    )

    columns, data = report.execute({"from_date": from_date, "to_date": to_date})[:2]
    if not data:
        return

    headers = ["Sales Person", "Target", "Planned", "Completed",
               "Completion %", "To Quotation", "Follow-ups Overdue"]
    keys = ["assigned_to", "target_visits", "planned", "completed",
            "completion_rate", "to_quotation", "followups_overdue"]

    body = [
        f"<p>{_('Visit performance for')} {from_date} &ndash; {to_date}</p>",
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;font-family:sans-serif;font-size:13px'>",
        "<tr style='background:#1F3864;color:#fff'>",
        "".join(f"<th>{_(h)}</th>" for h in headers),
        "</tr>",
    ]
    for r in data:
        body.append("<tr>" + "".join(
            f"<td align='{'left' if k == 'assigned_to' else 'right'}'>"
            f"{frappe.utils.escape_html(str(r.get(k) if r.get(k) is not None else ''))}</td>"
            for k in keys
        ) + "</tr>")
    body.append("</table>")
    body.append(
        f"<p style='color:#666;font-size:12px'>"
        f"{_('Fifteen minutes on this table every Monday is what keeps the data honest.')}"
        f"</p>")

    _email(
        settings.sales_manager,
        _("Weekly visit performance: {0} to {1}").format(from_date, to_date),
        "".join(body),
    )


# ------------------------------------------------------------------ helpers
def _notify(user, subject, message):
    try:
        note = frappe.new_doc("Notification Log")
        note.for_user = user
        note.type = "Alert"
        note.subject = subject
        note.email_content = message
        note.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Visit notification failed")


def _email(recipient, subject, message):
    try:
        frappe.sendmail(
            recipients=[recipient],
            subject=subject,
            message=message,
            reference_doctype="Customer Visit",
            now=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Visit digest email failed")
