# Testing and installing the Import Costing module

Same route as the Visit Management module: test on your local WSL bench first, then deploy through
Frappe Cloud.

## 1. Get the branch onto your local bench

```bash
cd ~/frappe-bench/apps/iaes_custom
git status                      # commit or stash anything pending first
git fetch origin feature/import-costing
git checkout feature/import-costing
cd ~/frappe-bench
bench --site visit.local migrate     # or your local test site
bench build --app iaes_custom
bench --site visit.local clear-cache
```

The `after_migrate` hook then:
- adds Import Duty % and IDL % to Customs Tariff Number, DHL Express Zone to Country, and Costing Sheet to Quotation
- fills Costing Settings: the DHL import rate card of 22 Oct 2026 and the Excel v3 exchange rates (dated 2 Nov, so
  they show as stale until you enter today's rates)
- sets the DHL zone on every country and creates the labour rates and three installation templates

It never overwrites values you have already edited.

## 2. Automated checks

```bash
bench --site visit.local set-config allow_tests true
bench --site visit.local run-tests --module iaes_custom.import_costing.tests.test_engine_fcc
bench --site visit.local run-tests --module iaes_custom.import_costing.doctype.costing_sheet.test_costing_sheet
```

These rebuild the FCC OPTY-08133 job from the Excel v3 workbook and expect TZS 336,659,000 for 10 boxes.
They create a few `_Test` records (company, customer, suppliers), so run them on a test site, not production.

## 3. Hand test checklist

1. **Costing Settings**: enter today's USD / EUR / ZAR rates with today's date; check VAT 18, RDL 2, CPF 1;
   on the Quotation tab pick the items used for selling groups and lump sums.
2. **Opportunity** → Create → **Costing Sheet**. Opportunity and customer fill in. Pick the quotation type and number of sets.
3. Get → **Items from RFQ** (every RFQ whose Opportunity is this one; or **Items from Opportunity**), then Get → **Supplier Quotations** (those linked to this Opportunity directly or through its RFQ).
4. A. Imported Goods: check the awarded supplier and Check column on each line; on Supplier shipments set the
   freight method (DHL Table, Per kg with a forwarder rate, or Fixed).
5. Try an **Award Override** without a reason: the sheet shows a blocking check. Add a reason: it clears.
6. C. Labour: Get → **Installation Template** → "Panel assembly per box", selling group = your box name.
7. Summary: selling lines, totals, GP %, and the Checks list.
8. **Submit**, then Create → **Quotation** (Grouped). The Quotation opens with one line per selling group.
9. Set an exchange-rate date older than 3 days: Recalculate shows it red, and Submit is refused.

## 4. Deploy

Merge the pull request into `main`. The live bench group picks up the push; after deploy the site migrates and the hook
sets everything up. `pyproject.toml` now declares Frappe `>=15.0.0,<16.0.0`, which Frappe Cloud requires.
