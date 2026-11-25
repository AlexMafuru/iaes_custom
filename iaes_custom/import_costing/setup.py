"""Import Costing module: custom fields and starting data.

Runs idempotently on every migrate and on fresh installs (same reasoning as
visit_management/setup.py: a patch would be skipped on a fresh install).
Existing values are never overwritten, so rates edited in Costing Settings
survive later migrations.

- Custom fields: Customs Tariff Number (duty %, IDL %), Country (DHL zone),
  Quotation (link back to the Costing Sheet)
- Costing Settings: DHL Express Worldwide Import rate card of 22 Oct 2026,
  starting exchange rates from the Excel v3 model (dated so they show as stale)
- Country DHL zones from the same rate card
- Labour rates and the first installation templates from the Excel LABOUR
  and Base sheets
"""

import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Import Costing"
DATA = os.path.join(os.path.dirname(__file__), "data")

CUSTOM_FIELDS = {
	"Customs Tariff Number": [
		{
			"fieldname": "import_duty_pct",
			"fieldtype": "Percent",
			"label": "Import Duty %",
			"insert_after": "description",
			"description": "EAC CET band: 0, 10, 25 or 35. Used by Costing Sheets when a supplier line has no duty override.",
			"module": MODULE,
		},
		{
			"fieldname": "idl_pct",
			"fieldtype": "Percent",
			"label": "IDL %",
			"insert_after": "import_duty_pct",
			"description": "Industrial Development Levy, only for goods listed under the IDL.",
			"module": MODULE,
		},
		{
			"fieldname": "duty_source",
			"fieldtype": "Data",
			"label": "Duty Source / Notes",
			"insert_after": "idl_pct",
			"module": MODULE,
		},
	],
	"Country": [
		{
			"fieldname": "dhl_zone",
			"fieldtype": "Int",
			"label": "DHL Express Zone",
			"insert_after": "code",
			"description": "Zone 1 to 8 on the DHL Express import rate card.",
			"module": MODULE,
		},
	],
	"Quotation": [
		{
			"fieldname": "costing_sheet",
			"fieldtype": "Link",
			"label": "Costing Sheet",
			"options": "Costing Sheet",
			"insert_after": "opportunity",
			"read_only": 1,
			"no_copy": 1,
			"module": MODULE,
		},
	],
}

LABOUR_RATES = [
	# role, day rate, notes  (from the Excel LABOUR / Base sheets)
	("Engineer (site)", 850000, "LABOUR table 1, site installation and commissioning"),
	("Engineer (assembly)", 1850000, "LABOUR table 2, panel assembly per box"),
	("Technician", 65000, ""),
	("Casual", 50000, ""),
	("Welder", 30000, ""),
]

TEMPLATES = [
	(
		"Site installation and commissioning",
		"From the Excel LABOUR sheet, table 1. Adjust people and days per job.",
		[
			dict(section="Labour", labour_rate="Engineer (site)", qty=1, days=7),
			dict(section="Labour", labour_rate="Technician", qty=0, days=0),
			dict(section="Labour", labour_rate="Casual", qty=0, days=0),
			dict(
				section="Site",
				cost_type="Accommodation",
				description="Accommodation",
				qty=1,
				days=0,
				rate=100000,
			),
			dict(
				section="Site",
				cost_type="Per diem",
				description="Meals and local transport",
				qty=2,
				days=2,
				rate=100000,
			),
			dict(
				section="Site",
				cost_type="Other",
				description="On-site commissioning",
				qty=2,
				days=2,
				rate=100000,
			),
		],
	),
	(
		"Panel assembly per box",
		"From the Excel LABOUR sheet, table 2: TZS 2,110,000 per box (Engineer 1 x 1 day + Technician 1 x 4 days).",
		[
			dict(section="Labour", labour_rate="Engineer (assembly)", qty=1, days=1, per_set=1),
			dict(section="Labour", labour_rate="Technician", qty=1, days=4, per_set=1),
		],
	),
	(
		"Panel base per box",
		"From the Excel Base sheet, table 2: TZS 210,000 per box. The FCC Summary used TZS 253,000 for the panel base; check before use.",
		[
			dict(section="Labour", labour_rate="Technician", qty=1, days=1, per_set=1),
			dict(section="Labour", labour_rate="Welder", qty=1, days=1, per_set=1),
			dict(section="Local goods", description="Angle iron", qty=1, days=1, rate=25000, per_set=1),
			dict(section="Local goods", description="Materials", qty=1, days=1, rate=90000, per_set=1),
		],
	),
]

# Starting exchange rates from the Excel v3 model. Deliberately dated in the
# past so the freshness check asks for current rates before any quotation.
START_FX = [
	("USD", 2650, "From the Excel v3 model - update to the current rate"),
	("EUR", 3213.89, "From the Excel v3 model - update"),
	("ZAR", 166.94, "From the Excel v3 model - update"),
]


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	seed_country_zones()
	seed_settings()
	seed_labour_rates()
	seed_templates()
	frappe.db.commit()


def load_dhl():
	with open(os.path.join(DATA, "dhl_import_2026_10_22.json")) as f:
		return json.load(f)


def seed_country_zones():
	zones = load_dhl()["zones"]
	for name, code, zone in frappe.get_all("Country", fields=["name", "code", "dhl_zone"], as_list=True):
		if zone or not code:
			continue
		z = zones.get(code.upper())
		if z:
			frappe.db.set_value("Country", name, "dhl_zone", z, update_modified=False)


def seed_settings():
	s = frappe.get_single("Costing Settings")
	changed = False
	if not s.dhl_rates:
		dhl = load_dhl()
		for row in dhl["rates"]:
			s.append(
				"dhl_rates",
				dict(row_type="Rate", weight_kg=row[0], **{f"zone_{z}": row[z] for z in range(1, 9)}),
			)
		for a in dhl["adders"]:
			s.append(
				"dhl_rates",
				dict(
					row_type="Adder",
					from_kg=a["from_kg"],
					to_kg=a["to_kg"],
					step_kg=a["step_kg"],
					**{f"zone_{z}": a["rates"][z - 1] for z in range(1, 9)},
				),
			)
		s.dhl_rate_card_date = dhl["rate_card_date"]
		s.dhl_discount_pct = dhl["discount_pct"]
		changed = True
	if not s.exchange_rates:
		for cur, rate, src in START_FX:
			if frappe.db.exists("Currency", cur):
				s.append(
					"exchange_rates",
					dict(currency=cur, rate=rate, buffer_pct=0, rate_date="2026-11-02", source=src),
				)
		changed = True
	# first-time defaults for fields still empty
	defaults = dict(
		fx_max_age_days=3,
		vat_pct=18,
		rdl_pct=2,
		cpf_pct=1,
		clearing_pct=0.2,
		transport_pct=0.1,
		tbs_amount=30000,
		dhl_switch_weight=20,
		default_freight_method="Per kg",
		approver_role="Sales Manager",
		margin_imported=40,
		margin_local=40,
		margin_labour=40,
		margin_site=40,
		margin_other=40,
	)
	if not s.vat_pct and not s.rdl_pct:
		for k, v in defaults.items():
			if not s.get(k):
				s.set(k, v)
		changed = True
	if changed:
		s.flags.ignore_mandatory = True
		s.save(ignore_permissions=True)


def seed_labour_rates():
	for role, rate, notes in LABOUR_RATES:
		if not frappe.db.exists("Costing Labour Rate", role):
			frappe.get_doc(
				dict(doctype="Costing Labour Rate", role_name=role, day_rate=rate, description=notes)
			).insert(ignore_permissions=True)


def seed_templates():
	for name, desc, rows in TEMPLATES:
		if frappe.db.exists("Installation Template", name):
			continue
		doc = frappe.get_doc(dict(doctype="Installation Template", template_name=name, description=desc))
		for r in rows:
			row = dict(r)
			if row.get("section") == "Labour" and not row.get("description"):
				row["description"] = row["labour_rate"]
			doc.append("items", row)
		doc.insert(ignore_permissions=True)
