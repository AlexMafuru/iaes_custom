"""
iaes_custom/hooks_pinv_task.py
==============================
Server-side logic that fires when a Purchase Invoice is submitted or cancelled.

What it does:
  - On PINV submit  -> increments Task.custom_pinv_total by the PINV net total
                    -> recalculates Task.custom_combined_cost (EC + PINV)
  - On PINV cancel  -> reverses both

Add to iaes_custom/hooks.py:

    doc_events = {
        "Purchase Invoice": {
            "on_submit": "iaes_custom.hooks_pinv_task.on_pinv_submit",
            "on_cancel":  "iaes_custom.hooks_pinv_task.on_pinv_cancel",
        }
    }
"""

import frappe
from frappe.utils import flt


def on_pinv_submit(doc, method=None):
    """On PINV submit: add net total to linked Task(s)."""
    _update_task_pinv_total(doc, sign=+1)


def on_pinv_cancel(doc, method=None):
    """On PINV cancel: subtract net total from linked Task(s)."""
    _update_task_pinv_total(doc, sign=-1)


def _update_task_pinv_total(pinv_doc, sign):
    """
    Collects {task_name: amount} from line items, falling back to the
    header task field if a line has no task set.
    """
    task_amounts = {}

    for item in (pinv_doc.items or []):
        task_name = item.get("task") or pinv_doc.get("task")
        if not task_name:
            continue
        task_amounts[task_name] = (
            task_amounts.get(task_name, 0.0)
            + flt(item.net_amount or item.amount)
        )

    if not task_amounts:
        return

    for task_name, amount in task_amounts.items():
        _apply_pinv_delta(task_name, amount * sign)


def _apply_pinv_delta(task_name, delta):
    """
    Reads -> increments -> writes Task.custom_pinv_total and
    recalculates Task.custom_combined_cost.
    No manual frappe.db.commit() - ERPNext manages the transaction.
    """
    if not frappe.db.exists("Task", task_name):
        frappe.log_error(
            "PINV linked to non-existent Task: {}".format(task_name),
            "PINV Task Link"
        )
        return

    if not frappe.db.has_column("tabTask", "custom_pinv_total"):
        frappe.log_error(
            "custom_pinv_total field missing on Task. "
            "Run bench migrate after importing task_cost_fields.json.",
            "PINV Task Link"
        )
        return

    # Read current values
    task_values = frappe.db.get_value(
        "Task", task_name,
        ["custom_pinv_total", "actual_expense"],
        as_dict=True
    )

    new_pinv_total    = max(flt(task_values.custom_pinv_total) + delta, 0)
    new_combined_cost = flt(task_values.actual_expense) + new_pinv_total

    frappe.db.set_value(
        "Task", task_name,
        {
            "custom_pinv_total":    new_pinv_total,
            "custom_combined_cost": new_combined_cost,
        },
        update_modified=False   # don't bump Task's modified timestamp
    )

    frappe.logger().info(
        "Task {} | PINV total: {:.2f} | Combined cost: {:.2f}".format(
            task_name, new_pinv_total, new_combined_cost
        )
    )