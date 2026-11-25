"""Checks the costing engine against the Excel v3 model for FCC OPTY-08133.

Inputs and expected figures were exported from
IAES_Import_Costing_Model_v3_FCC_OPTY-08133.xlsx (fixture next to this file).
Expected: cost per box TZS 20,193,333.10, SP per box TZS 33,665,900,
10 boxes = TZS 336,659,000 excl. VAT.

Runs without Frappe:  python -m unittest iaes_custom.import_costing.tests.test_engine_fcc
and under bench:      bench --site <site> run-tests --module iaes_custom.import_costing.tests.test_engine_fcc
"""

import json
import os
import unittest

from iaes_custom.import_costing import engine

FIXTURE = os.path.join(os.path.dirname(__file__), "fcc_opty_08133_v3.json")


def load_fcc():
	with open(FIXTURE) as f:
		return json.load(f)


def excel_dhl_table(fx):
	weights = [row[0] for row in fx["zones"]]
	rates = {z: [row[z] for row in fx["zones"]] for z in range(1, 9)}
	return {"weights": weights, "rates": rates}


def fcc_data(fx):
	st = fx["settings"]
	shipments, offers = [], []
	for s in fx["suppliers"]:
		ov = s["overrides"]

		def pick(key, default):
			return ov.get(key) if ov.get(key) is not None else default

		method = {
			"Courier table": engine.FREIGHT_DHL,
			"Fixed": engine.FREIGHT_FIXED,
			"Per kg": engine.FREIGHT_PER_KG,
		}[s["freight_method"]]
		shipments.append(
			dict(
				supplier=s["supplier"],
				currency=s["currency"],
				fx_rate=st["fx"][s["currency"]],
				zone=fx["countries"].get(s["origin"]),
				freight_method=method,
				freight_value=s["freight_value"],
				discount_pct=s["discount_pct"],
				default_duty_pct=s["default_duty_pct"],
				insurance_pct=pick("insurance_pct", st["insurance"]),
				clearing_pct=pick("clearing_pct", st["clearing"]),
				transport_pct=pick("transport_pct", st["transport"]),
				psi=pick("psi", st["psi"]),
				fixed_charges=pick("tbs", st["tbs"])
				+ pick("port", st["port"])
				+ pick("storage", st["storage"])
				+ pick("guarantee", st["guarantee"]),
			)
		)
		for i, ln in enumerate(s["lines"], 1):
			offers.append(
				dict(
					idx=i,
					supplier=s["supplier"],
					description=ln["description"],
					part_no=ln["part_no"],
					unit_price=ln["unit_price"],
					unit_weight=ln["unit_weight"],
					hs_code=ln["hs_code"],
					duty_pct=ln["duty_pct"],
					match_type=engine.MATCH_EXACT,
					_xl_unit_all=ln["xl_unit_all"],
					_xl_unit_awarded=ln["xl_unit_awarded"],
				)
			)

	imported, local, labour = [], [], []
	for n, it in enumerate(fx["items"], 1):
		if it["category"] == "Imported":
			imported.append(
				dict(
					idx=n,
					description=it["name"],
					part_no=it["article"],
					qty_per_set=it["qty_per_box"],
					award_override=it["award_override"] or "",
					selling_group="Remote IO Box",
					_xl=it,
				)
			)
		elif it["category"] == "Local":
			local.append(
				dict(
					idx=n,
					description=it["name"],
					qty_per_set=it["qty_per_box"],
					unit_cost=it["local_price"],
					selling_group="Remote IO Box",
					_xl=it,
				)
			)
		else:  # Labour: the LABOUR sheet table 2, panel assembly per box
			labour += [
				dict(
					idx=1,
					role="Engineer (assembly)",
					people=1,
					days=1,
					day_rate=1850000,
					per_set=1,
					selling_group="Remote IO Box",
				),
				dict(
					idx=2,
					role="Technician",
					people=1,
					days=4,
					day_rate=65000,
					per_set=1,
					selling_group="Remote IO Box",
				),
			]
	m = st["margin"]
	return dict(
		quotation_type=engine.QT_SUPPLY_INSTALL,
		sets=st["boxes"],
		rates=dict(rdl_pct=st["rdl"], cpf_pct=st["cpf"], vat_pct=st["vat"]),
		hs_register={},
		shipments=shipments,
		offers=offers,
		imported_items=imported,
		local_items=local,
		labour_items=labour,
		site_items=[],
		other_items=[],
		margins={
			"A": (m["Imported"], 0),
			"B": (m["Local"], 0),
			"C": (m["Labour"], 0),
			"D": (0.4, 0),
			"E": (0.4, 0),
		},
	)


class TestFCCAgainstExcelV3(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fx = load_fcc()
		cls.data = fcc_data(cls.fx)
		cls.res = engine.calculate(cls.data, {"dhl_table": excel_dhl_table(cls.fx)})

	def test_totals(self):
		r = self.res
		self.assertAlmostEqual(r["total_cost"] / 10, 20193333.1023066, places=2)
		self.assertEqual(r["total_sp"], 336659000)
		self.assertEqual(r["groups"]["Remote IO Box"]["rate"], 33665900)
		self.assertEqual(r["groups"]["Remote IO Box"]["qty"], 10)
		self.assertAlmostEqual(r["vat"], 60598620, places=2)

	def test_awarded_supplier_and_unit_cost_per_line(self):
		for it in self.data["imported_items"]:
			xl = it["_xl"]
			self.assertEqual(it["awarded_supplier"], xl["xl_awarded"], it["part_no"])
			self.assertAlmostEqual(it["unit_cost"], xl["xl_unit_cost"], places=4, msg=it["part_no"])
			self.assertEqual(it["unit_sp"], xl["xl_unit_sp"], it["part_no"])
		for it in self.data["local_items"]:
			self.assertEqual(it["unit_sp"], it["_xl"]["xl_unit_sp"])

	def test_every_supplier_line_both_passes(self):
		for o in self.data["offers"]:
			if o["_xl_unit_all"] in (None, "", 0):
				continue
			self.assertAlmostEqual(
				o["unit_all"], o["_xl_unit_all"], places=4, msg=(o["supplier"], o["part_no"])
			)
			self.assertAlmostEqual(
				o["unit_awarded"], o["_xl_unit_awarded"] or 0, places=4, msg=(o["supplier"], o["part_no"])
			)

	def test_shipment_landed_cost(self):
		for s in self.fx["suppliers"]:
			p1 = self.res["shipments"]["pass1"][s["supplier"]]
			p2 = self.res["shipments"]["pass2"][s["supplier"]]
			self.assertAlmostEqual(p1["landed"], s["xl"]["landed_all"], places=2, msg=s["supplier"])
			self.assertAlmostEqual(p2["landed"], s["xl"]["landed_aw"], places=2, msg=s["supplier"])
			self.assertAlmostEqual(p2["freight"], s["xl"]["freight_aw"], places=2, msg=s["supplier"])

	def test_labour_rounded_as_one_lump_like_excel(self):
		# Excel: Assembly Cost 2,110,000 per box -> SP 3,516,700
		b = self.res["buckets"]["C"][0]
		self.assertEqual(b["cost"], 2110000)
		self.assertEqual(b["sp"], 3516700)

	def test_freight_estimates_flagged(self):
		est = [c for c in self.res["checks"] if "ESTIMATE" in c["message"]]
		# Kalis (545 kg -> awarded weight) and Phoenix Contact are above the 70 kg table
		self.assertTrue(est)
		self.assertFalse(self.res["has_errors"], [c for c in self.res["checks"] if c["level"] == "Error"])


class TestRules(unittest.TestCase):
	def test_key_normalisation(self):
		self.assertEqual(engine.normalise_key("0806602"), "806602")
		self.assertEqual(engine.normalise_key(" 806 602\xa0"), "806602")
		self.assertEqual(engine.normalise_key("1492-fb2m30-l"), "1492-FB2M30-L")
		self.assertEqual(engine.normalise_key(806602.0), "806602")

	def test_roundup(self):
		self.assertEqual(engine.selling_price(295993.38, 0.4), 493400)
		self.assertEqual(engine.selling_price(60000, 0.4), 100000)

	def test_dhl_adders_match_rate_card(self):
		# DHL import card 22 Oct 2026, zone 1: 30 kg 876,242.00 ; 40 kg 1,081,537.00 ; adder 30.1-70 20,529.50
		table = {
			"weights": [30.0, 40.0, 70.0],
			"rates": {1: [876242.0, 1081537.0, 1697422.0]},
			"adders": [
				{"from_kg": 30, "to_kg": 70, "step_kg": 1, "rates": {1: 20529.5}},
				{"from_kg": 70, "to_kg": 300, "step_kg": 1, "rates": {1: 25710.8}},
			],
		}
		self.assertAlmostEqual(engine.dhl_rate(40, 1, table)[0], 1081537.0)
		self.assertAlmostEqual(engine.dhl_rate(31.2, 1, table)[0], 876242.0 + 2 * 20529.5)
		amt, est = engine.dhl_rate(100, 1, table)
		self.assertAlmostEqual(amt, 1697422.0 + 30 * 25710.8)
		self.assertFalse(est)
		table["discount_pct"] = 0.05
		self.assertAlmostEqual(engine.dhl_rate(40, 1, table)[0], 1081537.0 * 0.95)

	def test_override_needs_reason_and_alternative_needs_confirmation(self):
		data = dict(
			quotation_type=engine.QT_SUPPLY,
			sets=1,
			rates={},
			shipments=[
				dict(supplier="S1", fx_rate=1, freight_method=engine.FREIGHT_FIXED, freight_value=10),
				dict(supplier="S2", fx_rate=1, freight_method=engine.FREIGHT_FIXED, freight_value=10),
			],
			offers=[
				dict(idx=1, supplier="S1", part_no="A1", unit_price=100, unit_weight=1),
				dict(
					idx=2, supplier="S2", part_no="A1", unit_price=50, unit_weight=1, match_type="Alternative"
				),
			],
			imported_items=[dict(idx=1, part_no="a1", qty_per_set=1, award_override="")],
			margins={"A": (0.4, 0.2)},
		)
		r = engine.calculate(data, {})
		self.assertEqual(data["imported_items"][0]["awarded_supplier"], "S1")  # S2 not confirmed
		data["offers"][1]["engineer_confirmed"] = 1
		r = engine.calculate(data, {})
		self.assertEqual(data["imported_items"][0]["awarded_supplier"], "S2")
		data["imported_items"][0]["award_override"] = "S1"
		r = engine.calculate(data, {})
		self.assertTrue(any("Reason required" in c["message"] for c in r["checks"]))
		data["imported_items"][0]["override_reason"] = "Customer prefers original"
		r = engine.calculate(data, {})
		self.assertFalse(r["has_errors"])

	def test_no_freight_figure_blocks(self):
		data = dict(
			quotation_type=engine.QT_SUPPLY,
			sets=1,
			rates={},
			shipments=[dict(supplier="S1", fx_rate=1, freight_method=engine.FREIGHT_PER_KG, freight_value=0)],
			offers=[dict(idx=1, supplier="S1", part_no="A1", unit_price=100, unit_weight=1)],
			imported_items=[dict(idx=1, part_no="A1", qty_per_set=1)],
			margins={"A": (0.4, 0)},
		)
		r = engine.calculate(data, {})
		self.assertTrue(r["has_errors"])

	def test_margin_below_minimum_blocks(self):
		data = dict(
			quotation_type=engine.QT_INSTALL,
			sets=1,
			rates={},
			local_items=[
				dict(idx=1, description="Cable", qty_per_set=1, unit_cost=1000, margin_override=0.1)
			],
			labour_items=[dict(idx=1, people=2, days=3, day_rate=100000, per_set=0)],
			margins={"B": (0.3, 0.2), "C": (0.4, 0.25)},
		)
		r = engine.calculate(data, {})
		self.assertTrue(any("below minimum" in c["message"] for c in r["checks"]))
		self.assertEqual(r["sections"]["C"]["cost"], 600000)
		self.assertEqual(r["sections"]["C"]["sp"], 1000000)


if __name__ == "__main__":
	unittest.main()
