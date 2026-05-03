# -*- coding: utf-8 -*-
# Copyright (c) 2026, IAES and contributors
# License: MIT
#
# NMB Contract Price — DocType controller
# Holds Schedule III spare parts price list for the NMB HQ MEP contract
# (PROJ-0210, contract dated 16-Dec-2024, effective Nov 2024 – Oct 2027).
#
# One row per (project, item) combination. Looked up by the NMB HQ Monthly
# Billing report to compute Contract Margin and suggest billing mode.

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class NMBContractPrice(Document):
    def validate(self):
        if self.contract_unit_price is not None and self.contract_unit_price < 0:
            frappe.throw("Contract Unit Price cannot be negative.")

        if self.effective_from and self.effective_to:
            if self.effective_from > self.effective_to:
                frappe.throw("Effective From cannot be after Effective To.")
