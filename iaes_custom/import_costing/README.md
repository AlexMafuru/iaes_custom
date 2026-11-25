# Import Costing (module of iaes_custom)

Costs IAES quotations in ERPNext v15: Opportunity → Supplier Quotations → **Costing Sheet** → customer Quotation.
The calculation reproduces the Excel model `IAES_Import_Costing_Model_v3_FCC_OPTY-08133.xlsx` exactly
(FCC OPTY-08133: TZS 336,659,000 for 10 boxes excl. VAT, cost TZS 201,933,331).

## What is in the module

| DocType | Purpose |
|---|---|
| **Costing Sheet** (submittable, `CST-YYYY-#####`) | One costing per Opportunity. Sections A to E, switched by Quotation Type. |
| **Costing Settings** (single) | Exchange rates with FX buffer and date, VAT / RDL / CPF, default local charges, margins (target and minimum per section), freight defaults, DHL rate card, items used on the Quotation. |
| **Costing Labour Rate** | Roles and day rates (seeded from the Excel LABOUR / Base sheets). |
| **Installation Template** | Reusable packages of labour, site, local-goods and other rows (seeded: site installation, panel assembly per box, panel base per box). |

Custom fields (created on migrate): Customs Tariff Number → *Import Duty %*, *IDL %*, *Duty Source*;
Country → *DHL Express Zone*; Quotation → *Costing Sheet*.
Opportunity gets a **Create → Costing Sheet** button.

## Sections and quotation types

| Section | Supply only | Supply & Installation | Installation only |
|---|---|---|---|
| A. Imported goods | ✓ | ✓ | – |
| B. Local goods | ✓ | ✓ | ✓ (optional) |
| C. Labour | – | ✓ | ✓ |
| D. Site and installation | – | ✓ | ✓ |
| E. Other / one-off | ✓ | ✓ | ✓ |

## Calculation (engine.py)

Section A, per supplier shipment, two passes:

1. **All quoted lines** → landed unit cost per offer → cheapest *eligible* offer per requested line
   (Alternative / Replacement offers count only once an engineer ticks *Engineer Confirmed*).
2. **Awarded lines only** → freight, inspection and fixed charges recalculated on what is actually bought.
   This is the cost that is priced.

Per line: FOB = price × (1 − discount) × qty × FX; CIF = FOB × (1 + insurance) + inspection share (by value)
+ freight share (by weight, by value if no weights); then duty % and IDL % on CIF, RDL on CIF, CPF on FOB,
clearing and local transport on CIF, fixed charges shared by value.

Duty per line: *Duty % Override* on the offer, else the HS code's Import Duty %, else the shipment's default duty.
Part matching: by Item, else by part number ignoring spaces, case and leading zeros.

Selling price = cost / (1 − margin), rounded **up** to the nearest 100: per line for A and B (as in the Excel
Summary); for C, D and E once per bucket (section + selling group + per-set), so a labour table sold as one
lump gives the Excel figure (e.g. panel assembly 2,110,000 → 3,516,700 per box).

**Selling groups** sell many rows as one Quotation line (FCC: about 30 components + assembly = one box).

## Freight

Per shipment: *DHL Table*, *Per kg*, *Fixed*, or blank = default (DHL up to *Use DHL up to (kg)*, then the default
method with the origin's default per-kg rate). A price basis of CFR / CIF / CPT / CIP / DAP / DPU / DDP means the
supplier price already includes freight. Freight is never silently zero: no figure is a blocking check.

The DHL table holds the **DHL Express Worldwide Import** rate card of 22 Oct 2026 (non-documents) including the
official per-kg adders above 70 kg, the 5% account discount and a fuel surcharge % (enter the current one).
The DHL price is shown as a reference for any shipment within the table.

## Checks and blocks

Errors block **Submit** and **Make Quotation**: no price, no freight figure, no exchange rate, exchange rate older
than the limit (default 3 days), override without a reason, unconfirmed alternative forced, selling below cost,
margin below the section minimum. Warnings: freight estimate, missing weight, override not cheapest, offer not in
the requested items. A user with the approver role (default *Sales Manager*) can tick *Override Approved* with a reason.

## Make Quotation

From a submitted sheet: **Create → Quotation**, *Grouped* (one line per selling group) or *Itemised*. Labour, site
and other costs outside a group go as one lump-sum line each, using the items set in Costing Settings.

## Tests

```bash
# engine only, no site needed
python -m unittest iaes_custom.import_costing.tests.test_engine_fcc
# on a site
bench --site <site> run-tests --module iaes_custom.import_costing.tests.test_engine_fcc
bench --site <site> run-tests --module iaes_custom.import_costing.doctype.costing_sheet.test_costing_sheet
```
