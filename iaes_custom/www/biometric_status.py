"""
Controller for the biometric status page.

Place at: iaes_custom/www/biometric_status.py
Template : iaes_custom/www/biometric_status.html

Login required — this page exposes employee names and attendance data.
"""

import frappe


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.throw("Please log in to view this page.", frappe.PermissionError)

    context.no_cache = 1
    context.show_sidebar = False
    return context
