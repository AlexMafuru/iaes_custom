"""Import Costing calculation engine.

Pure Python with no Frappe imports, so it can be unit-tested on its own and
checked line by line against the Excel v3 model
(IAES_Import_Costing_Model_v3_FCC_OPTY-08133.xlsx). The Costing Sheet
controller turns the document into plain dicts, calls ``calculate`` and
writes the results back.

Calculation (matches Excel v3):

Section A - imported goods, two passes per supplier shipment
    pass 1  "all quoted" lines: used only to find the cheapest landed
            unit cost per requested line
    pass 2  "awarded" lines only: each supplier's freight, inspection and
            fixed charges are recalculated on what is actually bought.
            This awarded cost is what gets priced.

    For every line in a pass:
        FOB      = unit price x (1 - discount) x qty x FX rate
        CIF      = FOB x (1 + insurance %)
                   + pre-shipment inspection x FOB / shipment FOB
                   + freight x line weight / shipment weight
                     (by value when the shipment has no weights)
        charges  = CIF x (duty % + IDL % + RDL % + clearing % + transport %)
                   + FOB x CPF %
                   + fixed charges x FOB / shipment FOB
        landed   = CIF + charges ; unit landed = landed / qty

Selling price per line = unit cost / (1 - margin), rounded UP to the
nearest 100, times quantity. Labour, site and other costs are rounded per
bucket (section + selling group + per-set flag) so that a labour table
priced as one lump sum gives the same figure as the Excel "Assembly Cost"
line.
"""

from __future__ import annotations

import math
import re

# ---------------------------------------------------------------- constants

FREIGHT_DHL = "DHL Table"
FREIGHT_PER_KG = "Per kg"
FREIGHT_FIXED = "Fixed"
FREIGHT_INCLUDED = "Included in price"
FREIGHT_AUTO = ""  # blank = use the default method from Costing Settings

MATCH_EXACT = "Exact"
MATCH_ALTERNATIVE = "Alternative"
MATCH_REPLACEMENT = "Replacement"

# Incoterms where the supplier price already includes main carriage.
FREIGHT_INCLUDED_INCOTERMS = {"CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"}

SECTIONS = ("A", "B", "C", "D", "E")
SECTION_LABELS = {
	"A": "Imported goods",
	"B": "Local goods",
	"C": "Labour",
	"D": "Site and installation",
	"E": "Other costs",
}

QT_SUPPLY = "Supply only"
QT_SUPPLY_INSTALL = "Supply & Installation"
QT_INSTALL = "Installation only"

# Which sections each quotation type uses (B is optional for Installation only:
# it is kept on so local goods typed on an installation job are still costed).
SECTIONS_BY_TYPE = {
	QT_SUPPLY: {"A", "B", "E"},
	QT_SUPPLY_INSTALL: {"A", "B", "C", "D", "E"},
	QT_INSTALL: {"B", "C", "D", "E"},
}

ERROR = "Error"
WARNING = "Warning"

EPS = 1e-9


# ---------------------------------------------------------------- helpers


def flt(v) -> float:
	try:
		if v is None or v == "":
			return 0.0
		return float(v)
	except (TypeError, ValueError):
		return 0.0


def normalise_key(value) -> str:
	"""Part number / HS code key: ignores spaces, case and leading zeros.

	"0806602", "806602" and " 806 602 " all give "806602".
	"1492-fb2m30-l" gives "1492-FB2M30-L".
	"""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		value = int(value)
	s = str(value).replace("\xa0", " ")
	s = re.sub(r"\s+", "", s).upper()
	if not s:
		return ""
	if s.isdigit():
		s = s.lstrip("0") or "0"
	return s


def roundup_100(x: float) -> float:
	"""Excel ROUNDUP(x, -2) for positive values."""
	x = round(flt(x), 6)
	if x <= 0:
		return 0.0
	return math.ceil(x / 100.0 - EPS) * 100.0


def selling_price(cost: float, margin: float) -> float:
	if cost <= 0:
		return 0.0
	if margin >= 1:
		margin = 0.99
	return roundup_100(cost / (1.0 - margin))


# ---------------------------------------------------------------- freight


def _table_rate(weight: float, zone: int, table: dict):
	"""Plain table lookup: first listed weight >= shipment weight. None above the table."""
	weights = table.get("weights") or []
	rates = (table.get("rates") or {}).get(int(zone or 0)) or []
	for w, r in zip(weights, rates, strict=False):
		if w + EPS >= weight:
			return flt(r)
	return None


def dhl_rate(weight: float, zone: int, table: dict) -> tuple[float, bool]:
	"""DHL Express price for ``weight`` kg to/from ``zone``.

	``table`` = {
	    "weights": [0.5, 1, ...],                 # listed weights
	    "rates":   {zone: [rate per listed weight]},
	    "adders":  [{"from_kg": 70, "to_kg": 300, "step_kg": 1, "rates": {zone: adder}}],
	    "discount_pct": 0.05, "fuel_pct": 0.0,
	}
	Adder bands follow the DHL rate card: price = price(from_kg) + each started
	step above from_kg x adder. Without a band covering the weight, the listed
	table is used; above the table the price is extrapolated from the last 10 kg
	and flagged as an estimate (the Excel v3 behaviour).
	Returns (amount, is_estimate).
	"""
	weights = table.get("weights") or []
	rates = (table.get("rates") or {}).get(int(zone or 0)) or []
	if weight <= 0 or not weights or not rates:
		return 0.0, False
	base, estimate = _dhl_base(weight, int(zone), table, 0)
	factor = (1 - flt(table.get("discount_pct"))) * (1 + flt(table.get("fuel_pct")))
	return base * factor, estimate


def _dhl_base(weight, zone, table, depth):
	for band in table.get("adders") or []:
		lo, hi = flt(band.get("from_kg")), flt(band.get("to_kg"))
		step = flt(band.get("step_kg")) or 1.0
		if lo + EPS < weight <= hi + EPS and depth < 10:
			listed = _table_rate(weight, zone, table)
			# a listed weight that is exactly the shipment weight wins
			if listed is not None and any(abs(w - weight) < EPS for w in table["weights"]):
				return listed, False
			start, est = _dhl_base(lo, zone, table, depth + 1)
			steps = math.ceil((weight - lo) / step - EPS)
			return start + steps * flt((band.get("rates") or {}).get(zone)), est
	listed = _table_rate(weight, zone, table)
	if listed is not None:
		return listed, False
	weights = table["weights"]
	rates = table["rates"][zone]
	max_w, last = weights[-1], flt(rates[-1])
	ref = _table_rate(max_w - 10, zone, table)
	slope = (last - ref) / 10.0 if ref is not None else 0.0
	return last + (weight - max_w) * slope, True


def dhl_listed_max(table: dict) -> float:
	"""Heaviest weight listed in the rate table (70 kg on the DHL card)."""
	weights = table.get("weights") or []
	return weights[-1] if weights else 0.0


def dhl_max_weight(table: dict) -> float:
	"""Heaviest weight DHL can price without an estimate."""
	weights = table.get("weights") or []
	top = weights[-1] if weights else 0.0
	for band in table.get("adders") or []:
		top = max(top, flt(band.get("to_kg")))
	return top


def resolve_freight_method(ship: dict, weight: float, settings: dict) -> tuple[str, float]:
	"""Returns (method, rate_or_amount) after applying defaults from settings."""
	if ship.get("price_includes_freight"):
		return FREIGHT_INCLUDED, 0.0
	method = ship.get("freight_method") or FREIGHT_AUTO
	value = flt(ship.get("freight_value"))
	if method != FREIGHT_AUTO:
		if method == FREIGHT_PER_KG and value == 0:
			value = flt(ship.get("default_rate_per_kg"))
		return method, value
	switch = flt(settings.get("dhl_switch_weight"))
	if switch <= 0:
		switch = dhl_listed_max(settings.get("dhl_table") or {})
	if weight <= switch:
		return FREIGHT_DHL, 0.0
	if ship.get("auto_method") == FREIGHT_FIXED:
		return FREIGHT_FIXED, value
	return FREIGHT_PER_KG, value or flt(ship.get("default_rate_per_kg"))


def freight_amount(method: str, value: float, weight: float, fob: float, zone, table: dict):
	"""Returns (amount, is_estimate)."""
	if fob <= 0:
		return 0.0, False
	if method == FREIGHT_INCLUDED:
		return 0.0, False
	if method == FREIGHT_FIXED:
		return value, False
	if method == FREIGHT_PER_KG:
		return value * weight, False
	if method == FREIGHT_DHL:
		return dhl_rate(weight, zone, table)
	return 0.0, False


# ---------------------------------------------------------------- section A


def _duty_for_offer(offer: dict, ship: dict, hs_register: dict) -> tuple[float, float]:
	"""Typed rate wins; else HS register; else the shipment default. IDL from the register."""
	hs = normalise_key(offer.get("hs_code"))
	reg = hs_register.get(hs) if hs else None
	typed = offer.get("duty_pct")
	if typed is not None and typed != "":
		duty = flt(typed)
	elif reg is not None and reg.get("duty_pct") is not None:
		duty = flt(reg.get("duty_pct"))
	else:
		duty = flt(ship.get("default_duty_pct"))
	idl = flt(reg.get("idl_pct")) if reg else 0.0
	return duty, idl


def _shipment_pass(ship: dict, lines: list[dict], rates: dict, settings: dict) -> dict:
	"""Landed cost of one supplier shipment over ``lines`` (offers with qty > 0)."""
	fx = flt(ship.get("fx_rate"))
	disc = flt(ship.get("discount_pct"))
	for ln in lines:
		ln["_fob"] = flt(ln["unit_price"]) * (1 - disc) * ln["_qty"] * fx
		ln["_weight"] = flt(ln.get("unit_weight")) * ln["_qty"]
	fob = sum(ln["_fob"] for ln in lines)
	weight = sum(ln["_weight"] for ln in lines)

	method, value = resolve_freight_method(ship, weight, settings)
	freight, estimate = freight_amount(
		method, value, weight, fob, ship.get("zone"), settings.get("dhl_table") or {}
	)
	ins_pct = flt(ship.get("insurance_pct"))
	psi = flt(ship.get("psi")) if fob > 0 else 0.0
	fixed = flt(ship.get("fixed_charges")) if fob > 0 else 0.0
	clearing = flt(ship.get("clearing_pct"))
	transport = flt(ship.get("transport_pct"))
	rdl, cpf = flt(rates.get("rdl_pct")), flt(rates.get("cpf_pct"))

	tot = dict(duty=0.0, idl=0.0, rdl=0.0, cpf=0.0, clearing=0.0, transport=0.0, landed=0.0, cif=0.0)
	duty_by_rate: dict[float, float] = {}
	for ln in lines:
		share = ln["_fob"] / fob if fob else 0.0
		if weight > 0:
			fr = freight * ln["_weight"] / weight
		else:
			fr = freight * share
		cif = ln["_fob"] * (1 + ins_pct) + psi * share + fr
		duty_amt = cif * ln["_duty"]
		idl_amt = cif * ln["_idl"]
		charges = duty_amt + idl_amt + cif * (rdl + clearing + transport) + ln["_fob"] * cpf + fixed * share
		landed = cif + charges
		ln["_landed"] = landed
		ln["_unit"] = landed / ln["_qty"] if ln["_qty"] else 0.0
		tot["cif"] += cif
		tot["duty"] += duty_amt
		tot["idl"] += idl_amt
		tot["rdl"] += cif * rdl
		tot["cpf"] += ln["_fob"] * cpf
		tot["clearing"] += cif * clearing
		tot["transport"] += cif * transport
		tot["landed"] += landed
		key = round(ln["_duty"], 4)
		duty_by_rate[key] = duty_by_rate.get(key, 0.0) + duty_amt

	insurance = fob * ins_pct
	vat_info = (tot["cif"] + tot["duty"] + tot["idl"]) * flt(rates.get("vat_pct"))
	return dict(
		fob=fob,
		weight=weight,
		freight_method=method,
		freight=freight,
		freight_estimate=estimate,
		insurance=insurance,
		psi=psi,
		cif=tot["cif"],
		duty=tot["duty"],
		idl=tot["idl"],
		rdl=tot["rdl"],
		cpf=tot["cpf"],
		clearing=tot["clearing"],
		transport=tot["transport"],
		fixed=fixed,
		landed=tot["landed"],
		factor=(tot["landed"] / fob) if fob else 0.0,
		vat_info=vat_info,
		duty_by_rate=duty_by_rate,
	)


def calculate_imported(data: dict, settings: dict, checks: list) -> dict:
	sets = flt(data.get("sets")) or 1.0
	items = data.get("imported_items") or []
	ships = {s["supplier"]: s for s in (data.get("shipments") or [])}
	offers = data.get("offers") or []
	hs_register = data.get("hs_register") or {}
	rates = data.get("rates") or {}

	by_code, by_part = {}, {}
	for it in items:
		it["_qty"] = flt(it.get("qty_per_set")) * sets
		if it.get("item_code"):
			by_code.setdefault(it["item_code"], it)
		pk = normalise_key(it.get("part_no"))
		if pk:
			by_part.setdefault(pk, it)

	# ---- match offers to requested lines
	for off in offers:
		off["_item"] = None
		it = None
		if off.get("item_code") and off["item_code"] in by_code:
			it = by_code[off["item_code"]]
		if it is None:
			it = by_part.get(normalise_key(off.get("part_no")))
		ship = ships.get(off.get("supplier"))
		if it is None or ship is None or flt(off.get("unit_price")) <= 0:
			off["_qty"] = 0.0
			if it is None and flt(off.get("unit_price")) > 0:
				checks.append(_chk(WARNING, "offers", off, "Not in requested items - not costed"))
			if ship is None:
				checks.append(_chk(ERROR, "offers", off, "Supplier has no shipment row"))
			continue
		off["_item"] = it
		off["_qty"] = it["_qty"]
		off["_duty"], off["_idl"] = _duty_for_offer(off, ship, hs_register)

	priced = [o for o in offers if o["_item"] is not None and o["_qty"] > 0]

	# ---- pass 1: all quoted lines
	pass1 = {}
	for sup, ship in ships.items():
		lines = [o for o in priced if o["supplier"] == sup]
		pass1[sup] = _shipment_pass(ship, lines, rates, settings)
		for o in lines:
			o["unit_all"] = o["_unit"]

	# ---- selection: cheapest eligible offer per requested line
	for it in items:
		cands = [o for o in priced if o["_item"] is it]
		eligible = [
			o
			for o in cands
			if (o.get("match_type") or MATCH_EXACT) == MATCH_EXACT or o.get("engineer_confirmed")
		]
		cheapest = min(eligible, key=lambda o: o["unit_all"]) if eligible else None
		it["cheapest_supplier"] = cheapest["supplier"] if cheapest else ""
		it["lowest_unit_cost"] = cheapest["unit_all"] if cheapest else 0.0
		override = it.get("award_override") or ""
		chosen = cheapest
		if override:
			forced = [o for o in cands if o["supplier"] == override]
			if not forced:
				checks.append(_chk(ERROR, "imported_items", it, f"Award override {override} has no offer"))
				chosen = None
			else:
				chosen = min(forced, key=lambda o: o["unit_all"])
				if chosen not in eligible:
					checks.append(
						_chk(
							ERROR,
							"imported_items",
							it,
							"{} offer needs engineer confirmation".format(chosen.get("match_type")),
						)
					)
				if cheapest is None or override != cheapest["supplier"]:
					if not (it.get("override_reason") or "").strip():
						checks.append(
							_chk(ERROR, "imported_items", it, "Reason required: override is not the cheapest")
						)
					else:
						checks.append(_chk(WARNING, "imported_items", it, "Override (not cheapest)"))
		it["_chosen"] = chosen
		it["awarded_supplier"] = chosen["supplier"] if chosen else ""
		if chosen is None and not override:
			if cands:
				checks.append(_chk(ERROR, "imported_items", it, "Only unconfirmed alternatives offered"))
			else:
				checks.append(_chk(ERROR, "imported_items", it, "No price"))
	for o in offers:
		o["awarded"] = 1 if (o["_item"] is not None and o["_item"].get("_chosen") is o) else 0

	# ---- pass 2: awarded lines only
	pass2 = {}
	for sup, ship in ships.items():
		lines = [o for o in priced if o["supplier"] == sup and o["awarded"]]
		pass2[sup] = _shipment_pass(ship, lines, rates, settings)
		for o in lines:
			o["unit_awarded"] = o["_unit"]
		for o in priced:
			if o["supplier"] == sup and not o["awarded"]:
				o["unit_awarded"] = 0.0
		_shipment_checks(sup, ship, pass2[sup], lines, settings, checks)

	for o in offers:
		o.setdefault("unit_all", 0.0)
		o.setdefault("unit_awarded", 0.0)
		o["qty"] = o["_qty"]
		o["duty_used"] = o.get("_duty", 0.0)
		o["idl_used"] = o.get("_idl", 0.0)
		o["matched_row"] = o["_item"].get("idx") if o["_item"] is not None else None

	for it in items:
		it["unit_cost"] = it["_chosen"]["unit_awarded"] if it.get("_chosen") else 0.0

	# DHL reference for shipments within the courier table
	max_w = dhl_listed_max(settings.get("dhl_table") or {})
	for sup, ship in ships.items():
		p2 = pass2[sup]
		ref = 0.0
		if 0 < p2["weight"] <= max_w and ship.get("zone"):
			ref, _ = dhl_rate(p2["weight"], ship.get("zone"), settings.get("dhl_table") or {})
		p2["dhl_reference"] = ref

	return dict(pass1=pass1, pass2=pass2)


def _shipment_checks(sup, ship, p2, lines, settings, checks):
	if not lines:
		return
	if flt(ship.get("fx_rate")) <= 0:
		checks.append(
			_chk(ERROR, "shipments", ship, "{}: no exchange rate for {}".format(sup, ship.get("currency")))
		)
	method = p2["freight_method"]
	if method in (FREIGHT_DHL, FREIGHT_PER_KG):
		missing = [o for o in lines if flt(o.get("unit_weight")) <= 0]
		for o in missing:
			checks.append(_chk(WARNING, "offers", o, "No weight - freight shared by value"))
	if method != FREIGHT_INCLUDED and p2["freight"] <= 0:
		checks.append(
			_chk(ERROR, "shipments", ship, f"{sup}: no freight figure ({method}) - enter a rate or amount")
		)
	if p2["freight_estimate"]:
		level = ERROR if settings.get("block_freight_estimate") else WARNING
		checks.append(
			_chk(
				level,
				"shipments",
				ship,
				"{}: freight ESTIMATE - {:.1f} kg is above the {:.0f} kg courier table; use Per kg or Fixed".format(
					sup, p2["weight"], dhl_max_weight(settings.get("dhl_table") or {})
				),
			)
		)


def _chk(level, table, row, message):
	return dict(level=level, table=table, idx=row.get("idx"), message=message)


# ---------------------------------------------------------------- selling


def _line_selling(section, rows, margin_default, margin_min, sets, checks, table):
	"""Sections A and B: per-line rounding, like the Excel Summary sheet."""
	for r in rows:
		m = r.get("margin_override")
		m = flt(m) if m not in (None, "") else margin_default
		r["margin_used"] = m
		unit_cost = flt(r.get("unit_cost"))
		r["unit_sp"] = selling_price(unit_cost, m)
		qps = flt(r.get("qty_per_set"))
		r["cost_per_set"] = qps * unit_cost
		r["sp_per_set"] = qps * r["unit_sp"]
		r["total_cost"] = r["cost_per_set"] * sets
		r["total_sp"] = r["sp_per_set"] * sets
		if unit_cost > 0 and r["unit_sp"] < unit_cost - EPS:
			checks.append(_chk(ERROR, table, r, "Sells below cost"))
		elif unit_cost > 0 and m + EPS < margin_min:
			checks.append(
				_chk(ERROR, table, r, f"Margin {m * 100:.1f}% below minimum {margin_min * 100:.1f}%")
			)


def _bucket_selling(rows, margin, margin_min, sets, checks, table):
	"""Sections C, D, E: costs summed per (selling group, per-set) bucket and
	rounded once, so a labour table sold as one lump sum matches Excel."""
	buckets: dict[tuple, list] = {}
	for r in rows:
		buckets.setdefault((r.get("selling_group") or "", bool(r.get("per_set"))), []).append(r)
	out = []
	for (group, per_set), members in buckets.items():
		cost = sum(flt(r.get("amount")) for r in members)
		sp = selling_price(cost, margin)
		mult = sets if per_set else 1.0
		# informative per-line SP (unrounded share of the bucket)
		for r in members:
			r["sp_amount"] = sp * flt(r.get("amount")) / cost if cost else 0.0
			r["total_cost"] = flt(r.get("amount")) * mult
			r["total_sp"] = r["sp_amount"] * mult
		out.append(
			dict(group=group, per_set=per_set, cost=cost, sp=sp, total_cost=cost * mult, total_sp=sp * mult)
		)
	if margin + EPS < margin_min and rows:
		checks.append(
			_chk(
				ERROR, table, {}, f"Section margin {margin * 100:.1f}% below minimum {margin_min * 100:.1f}%"
			)
		)
	return out


def calculate(data: dict, settings: dict) -> dict:
	"""Main entry point.

	data keys: quotation_type, sets, rates, hs_register, shipments, offers,
	imported_items, local_items, labour_items, site_items, other_items,
	margins {A: (target, min), ...}, contingency_pct
	settings keys: dhl_table, dhl_switch_weight, block_freight_estimate
	"""
	checks: list[dict] = []
	sets = flt(data.get("sets")) or 1.0
	enabled = SECTIONS_BY_TYPE.get(data.get("quotation_type"), set(SECTIONS))
	margins = data.get("margins") or {}

	def mg(sec):
		t, mn = margins.get(sec, (0.0, 0.0))
		return flt(t), flt(mn)

	result = dict(sections={}, checks=checks, sets=sets)

	# A
	if "A" in enabled:
		imp = calculate_imported(data, settings, checks)
		result["shipments"] = imp
		_line_selling("A", data.get("imported_items") or [], *mg("A"), sets, checks, "imported_items")
	else:
		result["shipments"] = dict(pass1={}, pass2={})

	# B
	if "B" in enabled:
		for r in data.get("local_items") or []:
			if flt(r.get("unit_cost")) <= 0 and (r.get("description") or r.get("item_code")):
				checks.append(_chk(ERROR, "local_items", r, "No price"))
		_line_selling("B", data.get("local_items") or [], *mg("B"), sets, checks, "local_items")

	# C, D, E
	for r in data.get("labour_items") or []:
		r["amount"] = flt(r.get("people")) * flt(r.get("days")) * flt(r.get("day_rate"))
	for r in data.get("site_items") or []:
		days = flt(r.get("days")) if r.get("days") not in (None, "") else 1.0
		r["amount"] = flt(r.get("qty")) * (days or 1.0) * flt(r.get("rate"))
	for r in data.get("other_items") or []:
		r["amount"] = flt(r.get("qty")) * flt(r.get("rate"))

	site_rows = list(data.get("site_items") or [])
	contingency_pct = flt(data.get("contingency_pct"))
	contingency_row = None
	if "D" in enabled and contingency_pct and site_rows:
		base = sum(r["amount"] * (sets if r.get("per_set") else 1) for r in site_rows)
		contingency_row = dict(
			description="Contingency", amount=base * contingency_pct, per_set=0, selling_group=""
		)
		site_rows.append(contingency_row)

	buckets = {}
	for sec, key, table in (
		("C", "labour_items", "labour_items"),
		("D", None, "site_items"),
		("E", "other_items", "other_items"),
	):
		if sec not in enabled:
			continue
		rows = site_rows if sec == "D" else (data.get(key) or [])
		buckets[sec] = _bucket_selling(rows, *mg(sec), sets, checks, table)
	result["buckets"] = buckets
	result["contingency"] = contingency_row["amount"] if contingency_row else 0.0

	# ---- section totals
	def line_tot(rows):
		return (
			sum(flt(r.get("total_cost")) for r in rows),
			sum(flt(r.get("total_sp")) for r in rows),
			sum(flt(r.get("cost_per_set")) for r in rows),
			sum(flt(r.get("sp_per_set")) for r in rows),
		)

	for sec in SECTIONS:
		if sec not in enabled:
			result["sections"][sec] = dict(cost=0.0, sp=0.0)
			continue
		if sec == "A":
			c, s, _, _ = line_tot(data.get("imported_items") or [])
		elif sec == "B":
			c, s, _, _ = line_tot(data.get("local_items") or [])
		else:
			c = sum(b["total_cost"] for b in buckets.get(sec, []))
			s = sum(b["total_sp"] for b in buckets.get(sec, []))
		result["sections"][sec] = dict(cost=c, sp=s, gp=s - c, gp_pct=((s - c) / s) if s else 0.0)

	total_cost = sum(v["cost"] for v in result["sections"].values())
	total_sp = sum(v["sp"] for v in result["sections"].values())
	vat = total_sp * flt((data.get("rates") or {}).get("vat_pct"))
	result.update(
		total_cost=total_cost,
		total_sp=total_sp,
		gross_profit=total_sp - total_cost,
		gp_pct=((total_sp - total_cost) / total_sp) if total_sp else 0.0,
		vat=vat,
		total_incl_vat=total_sp + vat,
		has_errors=any(c["level"] == ERROR for c in checks),
	)
	result["groups"] = _group_totals(data, buckets, sets, enabled)
	return result


def _group_totals(data, buckets, sets, enabled):
	"""Selling groups: rows sold as one line (e.g. FCC: one Remote IO box)."""
	groups: dict[str, dict] = {}

	def g(name):
		return groups.setdefault(name, dict(sp_per_set=0.0, sp_job=0.0, cost_per_set=0.0, cost_job=0.0))

	for sec, key in (("A", "imported_items"), ("B", "local_items")):
		if sec not in enabled:
			continue
		for r in data.get(key) or []:
			if r.get("selling_group"):
				gg = g(r["selling_group"])
				gg["sp_per_set"] += flt(r.get("sp_per_set"))
				gg["cost_per_set"] += flt(r.get("cost_per_set"))
	for bl in buckets.values():
		for b in bl:
			if not b["group"]:
				continue
			gg = g(b["group"])
			if b["per_set"]:
				gg["sp_per_set"] += b["sp"]
				gg["cost_per_set"] += b["cost"]
			else:
				gg["sp_job"] += b["sp"]
				gg["cost_job"] += b["cost"]
	for gg in groups.values():
		gg["total_sp"] = gg["sp_per_set"] * sets + gg["sp_job"]
		gg["total_cost"] = gg["cost_per_set"] * sets + gg["cost_job"]
		if gg["sp_job"]:
			gg["qty"], gg["rate"] = 1.0, gg["total_sp"]
		else:
			gg["qty"], gg["rate"] = sets, gg["sp_per_set"]
	return groups
