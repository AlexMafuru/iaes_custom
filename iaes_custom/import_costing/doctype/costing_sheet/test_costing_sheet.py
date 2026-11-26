# Copyright (c) 2026, Alex and contributors
"""End-to-end check on a site: the FCC OPTY-08133 job entered as a Costing Sheet
must give the Excel v3 result (TZS 336,659,000 for 10 boxes excl. VAT).

bench --site <site> run-tests --module iaes_custom.import_costing.doctype.costing_sheet.test_costing_sheet
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from iaes_custom.import_costing.tests.test_engine_fcc import load_fcc

COMPANY = "_Test IAES Costing"
COUNTRY = {"China (CN)": "China", "South Africa (ZA)": "South Africa", "Spain (ES)": "Spain"}
METHOD = {"Courier table": "DHL Table", "Fixed": "Fixed", "Per kg": "Per kg"}


def make_company():
	if not frappe.db.exists("Company", COMPANY):
		frappe.get_doc(
			dict(
				doctype="Company",
				company_name=COMPANY,
				abbr="_TIC",
				default_currency="TZS",
				country="Tanzania",
			)
		).insert()


def make_group(doctype, name, parent):
	if not frappe.db.exists(doctype, name):
		field = frappe.scrub(doctype) + "_name"
		frappe.get_doc(
			{"doctype": doctype, field: name, "parent_" + frappe.scrub(doctype): parent, "is_group": 0}
		).insert()
	return name


def make_opportunity():
	if not frappe.db.exists("Customer", "_Test FCC"):
		frappe.get_doc(
			dict(
				doctype="Customer",
				customer_name="_Test FCC",
				customer_type="Company",
				customer_group=make_group("Customer Group", "_Test Costing", "All Customer Groups"),
				territory=make_group("Territory", "_Test Costing", "All Territories"),
			)
		).insert()
	return frappe.get_doc(
		dict(
			doctype="Opportunity",
			opportunity_from="Customer",
			party_name="_Test FCC",
			company=COMPANY,
			transaction_date=nowdate(),
		)
	).insert()


def use_excel_rates(fx):
	"""Costing Settings as in the Excel v3 Settings sheet, with its older courier table."""
	s = frappe.get_single("Costing Settings")
	st = fx["settings"]
	s.exchange_rates = []
	for cur, rate in st["fx"].items():
		s.append("exchange_rates", dict(currency=cur, rate=rate, buffer_pct=0, rate_date=nowdate()))
	s.vat_pct, s.rdl_pct, s.cpf_pct = 18, 2, 1
	s.clearing_pct, s.transport_pct, s.insurance_pct = 0.2, 0.1, 0
	s.psi_amount, s.tbs_amount, s.port_amount, s.storage_amount, s.guarantee_amount = 0, 30000, 0, 0, 0
	for k in ("imported", "local", "labour", "site", "other"):
		s.set("margin_" + k, 40)
		s.set("min_margin_" + k, 0)
	s.dhl_rates = []
	for row in fx["zones"]:
		s.append(
			"dhl_rates", dict(row_type="Rate", weight_kg=row[0], **{f"zone_{z}": row[z] for z in range(1, 9)})
		)
	s.dhl_discount_pct = 0
	s.dhl_fuel_surcharge_pct = 0
	s.dhl_switch_weight = 1000  # Excel used the courier table at any weight
	s.save()
	for xl_name, country in COUNTRY.items():
		frappe.db.set_value("Country", country, "dhl_zone", fx["countries"][xl_name])


class TestCostingSheet(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.fx = load_fcc()
		make_company()
		use_excel_rates(cls.fx)
		for s in cls.fx["suppliers"]:
			if not frappe.db.exists("Supplier", s["supplier"]):
				frappe.get_doc(
					dict(
						doctype="Supplier",
						supplier_name=s["supplier"],
						country=COUNTRY[s["origin"]],
						supplier_group=make_group("Supplier Group", "_Test Costing", "All Supplier Groups"),
					)
				).insert()

	def build_fcc(self):
		fx = self.fx
		opp = make_opportunity()
		cs = frappe.new_doc("Costing Sheet")
		cs.update(
			dict(
				opportunity=opp.name,
				company=COMPANY,
				quotation_type="Supply & Installation",
				sets=10,
				costing_date=nowdate(),
			)
		)
		for s in fx["suppliers"]:
			ov = s["overrides"]
			row = dict(
				supplier=s["supplier"],
				currency=s["currency"],
				origin=COUNTRY[s["origin"]],
				freight_method=METHOD[s["freight_method"]],
				freight_value=s["freight_value"] or 0,
				discount_pct=(s["discount_pct"] or 0) * 100,
				default_duty_pct=s["default_duty_pct"] * 100,
				use_default_charges=1,
			)
			if ov.get("clearing_pct") is not None:
				row.update(
					use_default_charges=0,
					insurance_pct=0,
					clearing_pct=ov["clearing_pct"] * 100,
					transport_pct=ov["transport_pct"] * 100,
					psi_amount=0,
					fixed_charges=30000,
				)
			cs.append("shipments", row)
			for ln in s["lines"]:
				cs.append(
					"offers",
					dict(
						supplier=s["supplier"],
						part_no=ln["part_no"],
						description=ln["description"],
						unit_price=ln["unit_price"],
						unit_weight=ln["unit_weight"] or 0,
					),
				)
		for it in fx["items"]:
			if it["category"] == "Imported":
				cs.append(
					"imported_items",
					dict(
						part_no=it["article"],
						description=it["name"],
						qty_per_set=it["qty_per_box"],
						selling_group="Remote IO Box",
					),
				)
			elif it["category"] == "Local":
				cs.append(
					"local_items",
					dict(
						description=it["name"],
						qty_per_set=it["qty_per_box"],
						unit_cost=it["local_price"],
						selling_group="Remote IO Box",
					),
				)
		cs.append(
			"labour_items",
			dict(
				labour_rate="Engineer (assembly)",
				people=1,
				days=1,
				day_rate=1850000,
				per_set=1,
				selling_group="Remote IO Box",
			),
		)
		cs.append(
			"labour_items",
			dict(
				labour_rate="Technician",
				people=1,
				days=4,
				day_rate=65000,
				per_set=1,
				selling_group="Remote IO Box",
			),
		)
		cs.insert()
		return cs

	def test_fcc_matches_excel_v3(self):
		cs = self.build_fcc()
		self.assertEqual(cs.error_count, 0, cs.checks_json)
		self.assertAlmostEqual(cs.total_cost, 201933331.02, delta=0.05)
		self.assertEqual(cs.total_selling, 336659000)
		self.assertAlmostEqual(cs.vat_amount, 60598620, places=2)
		box = cs.selling_groups[0]
		self.assertEqual((box.group_name, box.qty, box.rate), ("Remote IO Box", 10, 33665900))
		awarded = {r.part_no: r.awarded_supplier for r in cs.imported_items}
		self.assertEqual(awarded["1085176"], "neil")
		self.assertEqual(awarded["MAS0808030R5"], "Rittal")
		self.assertGreater(cs.warning_count, 0)  # freight estimates above the 70 kg courier table

	def test_stale_fx_blocks_submit(self):
		cs = self.build_fcc()
		s = frappe.get_single("Costing Settings")
		for r in s.exchange_rates:
			r.rate_date = "2026-01-01"
		s.save()
		try:
			cs.save()
			self.assertGreater(cs.error_count, 0)
			self.assertEqual(cs.status, "Blocked")
			self.assertRaises(frappe.ValidationError, cs.submit)
		finally:
			for r in s.exchange_rates:
				r.rate_date = nowdate()
			s.save()

	def test_make_quotation_grouped(self):
		item = "_Test Remote IO Box"
		if not frappe.db.exists("Item", item):
			frappe.get_doc(
				dict(
					doctype="Item",
					item_code=item,
					stock_uom="Nos",
					item_group=make_group("Item Group", "_Test Costing", "All Item Groups"),
					is_stock_item=0,
				)
			).insert()
		cs = self.build_fcc()
		cs.selling_groups[0].item_code = item
		cs.save()
		cs.submit()
		from iaes_custom.import_costing.doctype.costing_sheet.costing_sheet import make_quotation

		qn = make_quotation(cs.name, "Grouped")
		q = frappe.get_doc("Quotation", qn)
		self.assertEqual(len(q.items), 1)
		self.assertEqual(q.items[0].qty, 10)
		self.assertEqual(q.items[0].rate, 33665900)
		self.assertEqual(q.costing_sheet, cs.name)
		self.assertEqual(frappe.db.get_value("Costing Sheet", cs.name, "status"), "Quoted")

	def test_get_supplier_quotations(self):
		item = "_Test Costing Part 1085176"
		if not frappe.db.exists("Item", item):
			frappe.get_doc(
				dict(
					doctype="Item",
					item_code=item,
					stock_uom="Nos",
					is_stock_item=0,
					weight_per_unit=0.259,
					item_group=make_group("Item Group", "_Test Costing", "All Item Groups"),
				)
			).insert()
		opp = make_opportunity()
		opp.append("items", dict(item_code=item, qty=1, rate=1))
		opp.save()
		sq = frappe.get_doc(
			dict(
				doctype="Supplier Quotation",
				supplier="neil",
				company=COMPANY,
				currency="USD",
				conversion_rate=2650,
				opportunity=opp.name,
				transaction_date=nowdate(),
			)
		)
		sq.append("items", dict(item_code=item, qty=10, rate=93, uom="Nos", conversion_factor=1))
		sq.insert()
		cs = frappe.new_doc("Costing Sheet")
		cs.update(
			dict(
				opportunity=opp.name,
				company=COMPANY,
				quotation_type="Supply only",
				sets=10,
				costing_date=nowdate(),
			)
		)
		cs.insert()
		self.assertEqual(cs.get_opportunity_items(), 1)
		self.assertEqual(cs.get_supplier_quotations(), 1)
		cs.reload()
		self.assertEqual(len(cs.shipments), 1)
		self.assertEqual(cs.offers[0].unit_price, 93)
		self.assertAlmostEqual(cs.offers[0].unit_weight, 0.259)
		self.assertEqual(cs.imported_items[0].awarded_supplier, "neil")
		self.assertEqual(cs.imported_items[0].qty, 10)
		self.assertGreater(cs.imported_items[0].unit_cost, 93 * 2650)

	def test_items_and_quotations_from_rfq(self):
		from erpnext.buying.doctype.request_for_quotation.request_for_quotation import (
			make_supplier_quotation_from_rfq,
		)

		item = "_Test Costing Part 3240189"
		if not frappe.db.exists("Item", item):
			frappe.get_doc(
				dict(
					doctype="Item",
					item_code=item,
					stock_uom="Nos",
					is_stock_item=0,
					weight_per_unit=0.5,
					item_group=make_group("Item Group", "_Test Costing", "All Item Groups"),
				)
			).insert()
		opp = make_opportunity()
		rfq = frappe.get_doc(
			dict(
				doctype="Request for Quotation",
				company=COMPANY,
				opportunity=opp.name,
				transaction_date=nowdate(),
				message_for_supplier="Please quote",
			)
		)
		rfq.append("suppliers", dict(supplier="Phoenix Contact"))
		rfq.append(
			"items", dict(item_code=item, qty=10, uom="Nos", conversion_factor=1, schedule_date=nowdate())
		)
		rfq.insert()
		rfq.submit()
		sq = make_supplier_quotation_from_rfq(rfq.name, for_supplier="Phoenix Contact")
		sq.currency = "USD"
		sq.conversion_rate = 2650
		sq.opportunity = None  # reached through the RFQ only
		sq.items[0].rate = 19
		sq.insert()

		cs = frappe.new_doc("Costing Sheet")
		cs.update(
			dict(
				opportunity=opp.name,
				company=COMPANY,
				quotation_type="Supply only",
				sets=1,
				costing_date=nowdate(),
			)
		)
		cs.insert()
		self.assertEqual(cs.get_rfq_items(), 1)
		self.assertEqual(cs.get_rfq_items(), 0)  # no duplicates on a second click
		self.assertEqual(cs.get_supplier_quotations(), 1)
		cs.reload()
		self.assertEqual(cs.imported_items[0].item_code, item)
		self.assertEqual(cs.imported_items[0].qty_per_set, 10)
		self.assertEqual(cs.offers[0].unit_price, 19)
		self.assertEqual(cs.imported_items[0].awarded_supplier, "Phoenix Contact")
