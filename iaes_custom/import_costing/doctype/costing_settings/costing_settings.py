# Copyright (c) 2026, Alex and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CostingSettings(Document):
	def validate(self):
		seen = set()
		for r in self.exchange_rates:
			if r.currency in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(r.idx, r.currency))
			seen.add(r.currency)
			r.rate_used = flt(r.rate) * (1 + flt(r.buffer_pct) / 100.0)
		for r in self.dhl_rates:
			if r.row_type == "Adder" and flt(r.to_kg) <= flt(r.from_kg):
				frappe.throw(_("DHL row {0}: Adder To must be above Adder From").format(r.idx))
		for f in ("vat_pct", "rdl_pct", "cpf_pct", "clearing_pct", "transport_pct", "insurance_pct"):
			if flt(self.get(f)) < 0:
				frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(f)))

	def on_update(self):
		frappe.clear_document_cache("Costing Settings", "Costing Settings")
