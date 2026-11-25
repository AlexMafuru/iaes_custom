# Copyright (c) 2026, Alex and contributors
# For license information, please see license.txt
"""Costing Sheet: one costing per Opportunity, sections A to E.

All arithmetic lives in iaes_custom.import_costing.engine (pure Python, tested
against the Excel v3 model). This controller only moves data between the
document and the engine, applies defaults from Costing Settings, and guards
submit / Make Quotation.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, escape_html, flt, getdate, nowdate

from iaes_custom.import_costing import engine

PCT = 100.0  # Percent fields hold 0-100; the engine works in fractions

SECTION_MARGIN_KEYS = (("a", "imported"), ("b", "local"), ("c", "labour"), ("d", "site"), ("e", "other"))


def get_settings():
	return frappe.get_cached_doc("Costing Settings")


class CostingSheet(Document):
	# ------------------------------------------------------------ hooks
	def onload(self):
		self.set_onload("approver_role", get_settings().approver_role or "Sales Manager")

	def before_insert(self):
		self.set_margin_defaults(force=True)

	def validate(self):
		self.settings = get_settings()
		self.set_title()
		self.set_margin_defaults()
		self.validate_override_permission()
		self.set_shipment_defaults()
		self.calculate()
		self.set_status()

	def before_submit(self):
		if cint(self.error_count) and not cint(self.override_approved):
			frappe.throw(
				_(
					"This costing has {0} blocking check(s). Clear them, or ask a {1} to approve an override."
				).format(self.error_count, self.settings.approver_role or "Sales Manager"),
				title=_("Costing blocked"),
			)

	def on_submit(self):
		self.db_set("status", "Ready")

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ defaults
	def set_title(self):
		if not self.title:
			self.title = (
				f"{self.customer_name or self.party_name or self.opportunity} - {self.quotation_type}"
			)

	def set_margin_defaults(self, force=False):
		s = get_settings()
		for sec, key in SECTION_MARGIN_KEYS:
			if force or self.get("margin_" + sec) in (None, ""):
				self.set("margin_" + sec, flt(s.get("margin_" + key)))
			# the minimum always follows Costing Settings
			self.set("min_margin_" + sec, flt(s.get("min_margin_" + key)))

	def validate_override_permission(self):
		if not self.has_value_changed("override_approved"):
			return
		if cint(self.override_approved):
			role = self.settings.approver_role or "Sales Manager"
			if role not in frappe.get_roles() and frappe.session.user != "Administrator":
				frappe.throw(_("Only a {0} can approve an override.").format(role))
			self.override_by = frappe.session.user
		else:
			self.override_by = None

	def fx_table(self):
		out = {}
		for r in self.settings.exchange_rates:
			out[r.currency] = r
		return out

	def set_shipment_defaults(self):
		s = self.settings
		fx = self.fx_table()
		company_currency = "TZS"
		if self.company:
			company_currency = frappe.get_cached_value("Company", self.company, "default_currency") or "TZS"
		for sh in self.shipments:
			if sh.currency == company_currency:
				sh.fx_rate = 1
			elif sh.currency in fx:
				r = fx[sh.currency]
				sh.fx_rate = flt(r.rate) * (1 + flt(r.buffer_pct) / PCT)
			else:
				sh.fx_rate = 0
			if not sh.origin and sh.supplier:
				sh.origin = frappe.get_cached_value("Supplier", sh.supplier, "country")
			sh.zone = cint(frappe.get_cached_value("Country", sh.origin, "dhl_zone")) if sh.origin else 0
			if cint(sh.use_default_charges):
				sh.insurance_pct = flt(s.insurance_pct)
				sh.clearing_pct = flt(s.clearing_pct)
				sh.transport_pct = flt(s.transport_pct)
				sh.psi_amount = flt(s.psi_amount)
				sh.fixed_charges = (
					flt(s.tbs_amount) + flt(s.port_amount) + flt(s.storage_amount) + flt(s.guarantee_amount)
				)

	# ------------------------------------------------------------ engine
	def engine_settings(self):
		s = self.settings
		return dict(
			dhl_table=dhl_table_from_settings(s),
			dhl_switch_weight=flt(s.dhl_switch_weight),
			block_freight_estimate=cint(s.block_freight_estimate),
		)

	def engine_data(self):
		s = self.settings
		origin_rates = {r.country: flt(r.rate_per_kg) for r in (s.origin_freight_rates or [])}
		auto_method = s.default_freight_method or engine.FREIGHT_PER_KG

		shipments = []
		for sh in self.shipments:
			incoterm = (sh.incoterm or "").upper()[:3]
			shipments.append(
				dict(
					idx=sh.idx,
					supplier=sh.supplier,
					currency=sh.currency,
					fx_rate=flt(sh.fx_rate),
					zone=cint(sh.zone),
					freight_method=sh.freight_method or "",
					freight_value=flt(sh.freight_value),
					default_rate_per_kg=origin_rates.get(sh.origin, 0.0),
					auto_method=auto_method,
					price_includes_freight=incoterm in engine.FREIGHT_INCLUDED_INCOTERMS,
					discount_pct=flt(sh.discount_pct) / PCT,
					default_duty_pct=flt(sh.default_duty_pct) / PCT,
					insurance_pct=flt(sh.insurance_pct) / PCT,
					clearing_pct=flt(sh.clearing_pct) / PCT,
					transport_pct=flt(sh.transport_pct) / PCT,
					psi=flt(sh.psi_amount),
					fixed_charges=flt(sh.fixed_charges),
				)
			)

		hs_codes = {o.hs_code for o in self.offers if o.hs_code}
		hs_register = {}
		if hs_codes:
			for r in frappe.get_all(
				"Customs Tariff Number",
				filters={"name": ("in", list(hs_codes))},
				fields=["name", "import_duty_pct", "idl_pct"],
			):
				hs_register[engine.normalise_key(r.name)] = dict(
					duty_pct=flt(r.import_duty_pct) / PCT,
					idl_pct=flt(r.idl_pct) / PCT,
				)

		offers = []
		for o in self.offers:
			typed = (o.duty_override or "").strip().rstrip("%")
			offers.append(
				dict(
					idx=o.idx,
					supplier=o.supplier,
					item_code=o.item_code,
					part_no=o.part_no,
					unit_price=flt(o.unit_price),
					unit_weight=flt(o.unit_weight),
					hs_code=o.hs_code,
					duty_pct=(flt(typed) / PCT) if typed else None,
					match_type=o.match_type or engine.MATCH_EXACT,
					engineer_confirmed=cint(o.engineer_confirmed),
				)
			)

		def margin_override(v):
			return (flt(v) / PCT) if flt(v) else None

		imported = [
			dict(
				idx=r.idx,
				item_code=r.item_code,
				part_no=r.part_no,
				qty_per_set=flt(r.qty_per_set),
				award_override=r.award_override or "",
				override_reason=r.override_reason,
				margin_override=margin_override(r.margin_override),
				selling_group=r.selling_group,
			)
			for r in self.imported_items
		]
		local = [
			dict(
				idx=r.idx,
				item_code=r.item_code,
				description=r.description,
				qty_per_set=flt(r.qty_per_set),
				unit_cost=flt(r.unit_cost),
				margin_override=margin_override(r.margin_override),
				selling_group=r.selling_group,
			)
			for r in self.local_items
		]
		labour = [
			dict(
				idx=r.idx,
				people=r.people,
				days=r.days,
				day_rate=r.day_rate,
				per_set=cint(r.per_set),
				selling_group=r.selling_group,
			)
			for r in self.labour_items
		]
		site = [
			dict(
				idx=r.idx,
				qty=r.qty,
				days=r.days,
				rate=r.rate,
				per_set=cint(r.per_set),
				selling_group=r.selling_group,
			)
			for r in self.site_items
		]
		other = [
			dict(idx=r.idx, qty=r.qty, rate=r.rate, per_set=cint(r.per_set), selling_group=r.selling_group)
			for r in self.other_items
		]
		margins = {
			sec.upper(): (flt(self.get("margin_" + sec)) / PCT, flt(self.get("min_margin_" + sec)) / PCT)
			for sec, _key in SECTION_MARGIN_KEYS
		}
		return dict(
			quotation_type=self.quotation_type,
			sets=flt(self.sets) or 1,
			rates=dict(
				rdl_pct=flt(s.rdl_pct) / PCT, cpf_pct=flt(s.cpf_pct) / PCT, vat_pct=flt(s.vat_pct) / PCT
			),
			hs_register=hs_register,
			shipments=shipments,
			offers=offers,
			imported_items=imported,
			local_items=local,
			labour_items=labour,
			site_items=site,
			other_items=other,
			margins=margins,
			contingency_pct=flt(self.contingency_pct) / PCT,
		)

	def calculate(self):
		data = self.engine_data()
		res = engine.calculate(data, self.engine_settings())
		checks = res["checks"]
		self.add_document_checks(checks)

		# ---- write back section A
		for row, d in zip(self.imported_items, data["imported_items"], strict=True):
			row.qty = flt(row.qty_per_set) * res["sets"]
			for f in ("cheapest_supplier", "awarded_supplier"):
				row.set(f, d.get(f) or None)
			row.lowest_unit_cost = d.get("lowest_unit_cost", 0)
			row.unit_cost = d.get("unit_cost", 0)
			row.margin_used = flt(d.get("margin_used")) * PCT
			for f in ("unit_sp", "cost_per_set", "sp_per_set", "total_cost", "total_sp"):
				row.set(f, d.get(f, 0))
		for row, d in zip(self.offers, data["offers"], strict=True):
			row.qty = d.get("qty", 0)
			row.duty_used = flt(d.get("duty_used")) * PCT
			row.idl_used = flt(d.get("idl_used")) * PCT
			row.unit_landed_all = d.get("unit_all", 0)
			row.unit_landed_awarded = d.get("unit_awarded", 0)
			row.awarded = d.get("awarded", 0)
			row.matched_row = d.get("matched_row") or 0
		p1 = res["shipments"]["pass1"]
		p2 = res["shipments"]["pass2"]
		for sh in self.shipments:
			a, b = p2.get(sh.supplier) or {}, p1.get(sh.supplier) or {}
			for f in (
				"fob",
				"weight",
				"freight",
				"cif",
				"duty",
				"idl",
				"rdl",
				"cpf",
				"clearing",
				"transport",
				"fixed",
				"landed",
				"factor",
				"vat_info",
				"dhl_reference",
			):
				sh.set(f, flt(a.get(f)))
			sh.freight_method_used = a.get("freight_method") or ""
			sh.freight_estimate = 1 if a.get("freight_estimate") else 0
			sh.fob_all = flt(b.get("fob"))
			sh.landed_all = flt(b.get("landed"))

		# ---- B to E
		for row, d in zip(self.local_items, data["local_items"], strict=True):
			row.margin_used = flt(d.get("margin_used")) * PCT
			for f in ("unit_sp", "cost_per_set", "sp_per_set", "total_cost", "total_sp"):
				row.set(f, d.get(f, 0))
		for table, key in (
			("labour_items", "labour_items"),
			("site_items", "site_items"),
			("other_items", "other_items"),
		):
			for row, d in zip(self.get(table), data[key], strict=True):
				row.amount = d.get("amount", 0)
				row.sp_amount = d.get("sp_amount", 0)
				row.total_cost = d.get("total_cost", 0)

		# ---- totals
		for sec in "ABCDE":
			v = res["sections"].get(sec) or {}
			self.set("cost_" + sec.lower(), flt(v.get("cost")))
			self.set("sp_" + sec.lower(), flt(v.get("sp")))
		self.total_cost = res["total_cost"]
		self.total_selling = res["total_sp"]
		self.gross_profit = res["gross_profit"]
		self.gp_pct = res["gp_pct"] * PCT
		self.vat_amount = res["vat"]
		self.total_incl_vat = res["total_incl_vat"]

		# ---- selling groups
		groups = res["groups"]
		known = {g.group_name for g in self.selling_groups}
		for name in groups:
			if name not in known:
				self.append(
					"selling_groups", {"group_name": name, "item_code": self.settings.default_group_item}
				)
		for g in self.selling_groups:
			v = groups.get(g.group_name)
			g.qty = v["qty"] if v else 0
			g.rate = v["rate"] if v else 0
			g.amount = v["total_sp"] if v else 0
			g.cost = v["total_cost"] if v else 0

		self.store_checks(checks)

	def add_document_checks(self, checks):
		s = self.settings
		max_age = cint(s.fx_max_age_days)
		fx = self.fx_table()
		used = {sh.currency for sh in self.shipments if any(o.supplier == sh.supplier for o in self.offers)}
		for cur in sorted(c for c in used if c in fx):
			r = fx[cur]
			if not r.rate_date:
				checks.append(
					dict(
						level=engine.ERROR,
						table="settings",
						idx=None,
						message=_("{0} exchange rate has no date in Costing Settings").format(cur),
					)
				)
			elif max_age and date_diff(self.costing_date or nowdate(), r.rate_date) > max_age:
				checks.append(
					dict(
						level=engine.ERROR,
						table="settings",
						idx=None,
						message=_("{0} exchange rate dated {1} is older than {2} days").format(
							cur, frappe.format(getdate(r.rate_date), "Date"), max_age
						),
					)
				)
		if not self.opportunity:
			checks.append(dict(level=engine.ERROR, table="", idx=None, message=_("No Opportunity linked")))

	def store_checks(self, checks):
		# status text per imported row
		by_row = {}
		for c in checks:
			if c.get("table") == "imported_items" and c.get("idx"):
				by_row.setdefault(c["idx"], []).append(c["message"])
		for row in self.imported_items:
			msgs = by_row.get(row.idx)
			row.check_status = "; ".join(msgs)[:140] if msgs else "OK"

		self.error_count = sum(1 for c in checks if c["level"] == engine.ERROR)
		self.warning_count = sum(1 for c in checks if c["level"] == engine.WARNING)
		self.checks_json = json.dumps(checks)
		self.checks_html = render_checks(checks)

	def set_status(self):
		if self.docstatus == 0:
			self.status = (
				"Blocked" if cint(self.error_count) and not cint(self.override_approved) else "Draft"
			)

	# ------------------------------------------------------------ actions
	@frappe.whitelist()
	def get_supplier_quotations(self):
		"""Add every non-cancelled Supplier Quotation linked to the Opportunity."""
		if not self.opportunity:
			frappe.throw(_("Set the Opportunity first."))
		existing = {sh.supplier_quotation for sh in self.shipments if sh.supplier_quotation}
		sqs = frappe.get_all(
			"Supplier Quotation",
			filters={"opportunity": self.opportunity, "docstatus": ("<", 2)},
			fields=["name", "supplier", "currency", "incoterm"],
			order_by="creation asc",
		)
		added = 0
		for sq in sqs:
			if sq.name in existing:
				continue
			sq_doc = frappe.get_doc("Supplier Quotation", sq.name)
			if not any(sh.supplier == sq.supplier for sh in self.shipments):
				self.append(
					"shipments",
					{
						"supplier": sq.supplier,
						"supplier_quotation": sq.name,
						"currency": sq.currency,
						"incoterm": sq.incoterm,
						"origin": frappe.get_cached_value("Supplier", sq.supplier, "country"),
						"use_default_charges": 1,
						"default_duty_pct": 10,
					},
				)
			for it in sq_doc.items:
				self.append(
					"offers",
					{
						"supplier": sq.supplier,
						"item_code": it.item_code,
						"part_no": it.manufacturer_part_no or it.item_code,
						"description": frappe.utils.strip_html(it.description or it.item_name or "")[:500],
						"match_type": "Exact",
						"unit_price": flt(it.rate) / (flt(it.conversion_factor) or 1),
						"unit_weight": flt(it.weight_per_unit)
						or flt(frappe.get_cached_value("Item", it.item_code, "weight_per_unit")),
						"hs_code": frappe.get_cached_value("Item", it.item_code, "customs_tariff_number"),
						"supplier_quotation_item": it.name,
					},
				)
			added += 1
		self.save()
		return added

	@frappe.whitelist()
	def get_opportunity_items(self):
		"""Copy the Opportunity's items into section A as requested lines (qty = qty per set)."""
		opp = frappe.get_doc("Opportunity", self.opportunity)
		have = {r.item_code for r in self.imported_items if r.item_code}
		n = 0
		for it in opp.items:
			if it.item_code in have:
				continue
			self.append(
				"imported_items",
				{
					"item_code": it.item_code,
					"part_no": it.item_code,
					"description": frappe.utils.strip_html(it.description or it.item_name or "")[:500],
					"qty_per_set": flt(it.qty) or 1,
					"uom": it.uom,
				},
			)
			n += 1
		self.save()
		return n

	@frappe.whitelist()
	def apply_installation_template(self, template, selling_group=None):
		tpl = frappe.get_doc("Installation Template", template)
		for r in tpl.items:
			common = {"description": r.description, "per_set": r.per_set, "selling_group": selling_group}
			if r.section == "Labour":
				rate = flt(r.rate) or flt(
					frappe.db.get_value("Costing Labour Rate", r.labour_rate, "day_rate")
				)
				self.append(
					"labour_items",
					dict(common, labour_rate=r.labour_rate, people=r.qty, days=r.days, day_rate=rate),
				)
			elif r.section == "Site":
				self.append(
					"site_items",
					dict(common, cost_type=r.cost_type or "Other", qty=r.qty, days=r.days, rate=r.rate),
				)
			elif r.section == "Local goods":
				self.append(
					"local_items",
					dict(
						common,
						qty_per_set=flt(r.qty) * (flt(r.days) or 1),
						unit_cost=r.rate,
						supplier_note=template,
					),
				)
			else:
				self.append("other_items", dict(common, qty=flt(r.qty) * (flt(r.days) or 1), rate=r.rate))
		self.save()
		return len(tpl.items)


# ---------------------------------------------------------------- helpers


def dhl_table_from_settings(s):
	weights, rates, adders = [], {z: [] for z in range(1, 9)}, []
	rows = sorted([r for r in s.dhl_rates if r.row_type == "Rate"], key=lambda r: flt(r.weight_kg))
	for r in rows:
		weights.append(flt(r.weight_kg))
		for z in range(1, 9):
			rates[z].append(flt(r.get(f"zone_{z}")))
	for r in s.dhl_rates:
		if r.row_type == "Adder":
			adders.append(
				dict(
					from_kg=flt(r.from_kg),
					to_kg=flt(r.to_kg),
					step_kg=flt(r.step_kg) or 1,
					rates={z: flt(r.get(f"zone_{z}")) for z in range(1, 9)},
				)
			)
	adders.sort(key=lambda a: a["from_kg"])
	return dict(
		weights=weights,
		rates=rates,
		adders=adders,
		discount_pct=flt(s.dhl_discount_pct) / PCT,
		fuel_pct=flt(s.dhl_fuel_surcharge_pct) / PCT,
	)


TABLE_LABELS = {
	"imported_items": "A. Imported item",
	"offers": "A. Supplier offer",
	"shipments": "A. Shipment",
	"local_items": "B. Local goods",
	"labour_items": "C. Labour",
	"site_items": "D. Site costs",
	"other_items": "E. Other costs",
	"settings": "Costing Settings",
}


def render_checks(checks):
	if not checks:
		return '<div class="text-success">{}</div>'.format(_("All checks OK"))
	rows = []
	for c in sorted(
		checks, key=lambda c: (c["level"] != engine.ERROR, c.get("table") or "", c.get("idx") or 0)
	):
		colour = "red" if c["level"] == engine.ERROR else "orange"
		where = TABLE_LABELS.get(c.get("table"), "")
		if c.get("idx"):
			where += " row {}".format(c["idx"])
		rows.append(
			'<tr><td><span class="indicator-pill {}">{}</span></td><td>{}</td><td>{}</td></tr>'.format(
				colour, _(c["level"]), escape_html(where), escape_html(c["message"])
			)
		)
	return '<table class="table table-bordered table-sm"><tbody>{}</tbody></table>'.format("".join(rows))


# ---------------------------------------------------------------- Make Quotation


@frappe.whitelist()
def make_quotation(source_name, mode="Grouped"):
	"""Create a draft customer Quotation from a submitted Costing Sheet.

	mode = "Grouped": rows with a Selling Group become one line per group;
	       "Itemised": every imported/local row is its own line.
	Labour, site and other costs not in a group always go as one lump-sum
	line per section (items set in Costing Settings).
	"""
	cs = frappe.get_doc("Costing Sheet", source_name)
	cs.check_permission("read")
	if cs.docstatus != 1:
		frappe.throw(_("Submit the Costing Sheet first."))
	if cint(cs.error_count) and not cint(cs.override_approved):
		frappe.throw(_("The Costing Sheet has blocking checks."))
	if cs.quotation and frappe.db.get_value("Quotation", cs.quotation, "docstatus") != 2:
		frappe.throw(_("Quotation {0} already exists for this costing.").format(cs.quotation))

	s = get_settings()
	opp = frappe.get_doc("Opportunity", cs.opportunity)
	q = frappe.new_doc("Quotation")
	q.quotation_to = opp.opportunity_from
	q.party_name = opp.party_name
	q.opportunity = opp.name
	q.company = cs.company
	q.transaction_date = nowdate()
	q.currency = frappe.get_cached_value("Company", cs.company, "default_currency")
	q.conversion_rate = 1
	q.ignore_pricing_rule = 1
	q.order_type = "Sales"
	q.costing_sheet = cs.name

	grouped = mode != "Itemised"
	used_groups = set()

	def add(item_code, qty, rate, description=None, uom=None):
		if not item_code:
			frappe.throw(_("Missing Item for quotation line: {0}").format(description or ""))
		row = {
			"item_code": item_code,
			"qty": qty,
			"rate": rate,
			"prevdoc_doctype": "Opportunity",
			"prevdoc_docname": opp.name,
		}
		if description:
			row["description"] = description
		if uom:
			row["uom"] = uom
		q.append("items", row)

	for table in ("imported_items", "local_items"):
		for r in cs.get(table):
			if grouped and r.selling_group:
				used_groups.add(r.selling_group)
				continue
			if not flt(r.total_sp):
				continue
			add(r.item_code, flt(r.qty_per_set) * flt(cs.sets), r.unit_sp, r.description, r.uom)

	lump = {
		"labour_items": s.installation_item,
		"site_items": s.site_item or s.installation_item,
		"other_items": s.other_item,
	}
	labels = {
		"labour_items": _("Installation and commissioning"),
		"site_items": _("Site costs"),
		"other_items": _("Other costs"),
	}
	lump_amount = {}
	for table, sec in (("labour_items", "c"), ("site_items", "d"), ("other_items", "e")):
		grouped_sp = 0.0
		for r in cs.get(table):
			if r.selling_group:
				used_groups.add(r.selling_group)
				grouped_sp += flt(r.sp_amount) * (flt(cs.sets) if cint(r.per_set) else 1)
		rest = flt(cs.get("sp_" + sec)) - grouped_sp
		if rest > 0.5:  # includes the site contingency, which is never grouped
			lump_amount[table] = rest

	for g in cs.selling_groups:
		if g.group_name in used_groups and flt(g.amount):
			add(g.item_code or s.default_group_item, g.qty, g.rate, g.description or g.group_name, g.uom)
	for table, amount in lump_amount.items():
		add(lump[table], 1, amount, labels[table])

	q.insert()
	cs.db_set("quotation", q.name)
	cs.db_set("status", "Quoted")
	return q.name
