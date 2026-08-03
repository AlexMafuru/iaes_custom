// iaes_custom :: Unified List-View Utilities
// =============================================================================
// ONE file, ALL doctypes. Replaces three overlapping scripts:
//
//   1. listview_calculator.js        (app, app_include_js)  -- floating panel
//   2. sales_invoice_list_utils.js   (app, doctype_list_js) -- SINV summary/totals
//   3. Client Script CustomScript0004 (database)            -- PINV summary/totals
//
// Every configured doctype gets exactly two inner buttons in the list header:
//   "<Party> Summary"  -- grouped table, per-column filters, sorting, CSV
//   "<Doc> Totals"     -- floating, draggable figures panel
//
// The floating blue calculator icon is RETIRED. After deploying this file:
//   - delete iaes_custom/public/js/listview_calculator.js
//   - delete iaes_custom/public/js/sales_invoice_list_utils.js
//   - delete Client Scripts CustomScript0004 and CustomScript0009
//   - update hooks.py (see REGISTRATION below)
//
// REGISTRATION -- hooks.py:
//   app_include_js = [
//       "/assets/iaes_custom/js/iaes_listview_utils.js",
//   ]
//   # and REMOVE the old listview_calculator.js entry plus any
//   # doctype_list_js = {"Sales Invoice": "public/js/sales_invoice_list_utils.js"}
//
// -----------------------------------------------------------------------------
// CORRECTNESS NOTES -- these are the bugs this file exists to not repeat:
//
// 1. CHILD-TABLE DEDUPE. Filtering a parent doctype on a child-table field
//    (Purchase Order on Purchase Invoice Item, Reference on Payment Entry, Item
//    Code on any of them) makes the server JOIN the child table and return the
//    SAME parent once per matching child row. The list header applies DISTINCT;
//    a naive sum does not. Every fetch here collapses on `name` first.
//
// 2. ROUNDED TOTAL. On submit ERPNext sets
//        outstanding_amount = flt(rounded_total or grand_total)
//    so on a site with Rounded Total enabled, outstanding tracks the ROUNDED
//    figure while grand_total stays unrounded. Computing Paid as
//    grand_total - outstanding_amount therefore returns the accumulated rounding
//    difference (a small negative) instead of 0.00. Paid is measured against
//    base_rounded_total || base_grand_total -- the same base ERPNext used.
//
// 3. CURRENCY. Everything totals in COMPANY currency via base_* fields.
//    outstanding_amount has no base_ twin, and it is denominated in the PARTY
//    ACCOUNT currency (fieldtype Currency, options "party_account_currency") --
//    NOT the document currency. Those differ constantly: a EUR invoice booked
//    against a TZS creditors account stores outstanding_amount in TZS already.
//    Blindly multiplying by conversion_rate inflated a real PINV of EUR
//    29,187.90 from 91,734,650.91 TZS to 288,313,822,127.08 -- a 3,142x error,
//    exactly the EUR->TZS rate. So: convert ONLY when party_account_currency is
//    present AND differs from company currency; otherwise the figure is already
//    in company currency. When the field is absent, DO NOT convert -- that is
//    the safe default. The company currency is read from system defaults, never
//    hardcoded.
//
// 4. LISTVIEW_SETTINGS IS LAST-WRITER-WINS. frappe.listview_settings is a single
//    shared object. HRMS (expense_claim_list.js) and ERPNext (*_list.js) assign
//    their entry WHOLESALE, and those bundles load AFTER app_include_js -- so a
//    merge performed here is silently discarded before the list ever renders.
//    Registration therefore uses TWO paths (see WIRING at the bottom):
//      PATH 1  merge into frappe.listview_settings.onload   -- works when nobody
//              overwrites the slot afterwards
//      PATH 2  attach directly to the live ListView on route change -- immune to
//              any app clobbering listview_settings
//    Both funnel through add_buttons(), whose __iaes_utils_wired flag makes
//    double-wiring impossible.
//
// 5. NOT EVERY DOCTYPE HAS EVERY FIELD. Quotation has no `project` docfield, and
//    frappe.client.get_list rejects the WHOLE request with
//        "Field not permitted in query: project"
//    rather than ignoring the unknown column -- so one absent field kills the
//    entire feature for that doctype. fetch_rows() therefore filters the
//    requested field list against frappe.get_meta() before calling, and the
//    Summary dialog drops the Project(s) column when the field was not fetched.
//
// 6. ROW ALIGNMENT ACROSS LIST COLUMNS. PINV(s), Project(s) and Project
//    Customer(s) used to be three INDEPENDENT deduplicated sets, each in its own
//    order (insertion order for projects, alphabetical for customers). Reading
//    across a row therefore paired the wrong values together -- PINV-05164-1
//    (PROJ-0366, TPC) lined up against "Tanzania Distilleries Ltd". They are now
//    rendered from one per-document `entries` list, one fixed-height line each,
//    so line N of every list column is the same document. Do not "tidy" these
//    back into deduplicated sets.
// =============================================================================

frappe.provide("iaes");

iaes.listview_utils = (function () {

    "use strict";

    const BUILD = "2026-08-02-v7";
    console.log("[IAES listview utils] build", BUILD, "loaded");

    // Cap on ROWS fetched, not documents. A child-table filter fans out one row
    // per matching child line, so this must sit well above the document count.
    const MAX_ROWS = 20000;

    // =========================================================================
    // PRIMITIVES
    // =========================================================================

    function company_currency() {
        return frappe.defaults.get_global_default("currency")
            || (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency)
            || "";
    }

    function money(v) {
        return format_currency(flt(v), company_currency());
    }

    function esc(v) {
        return frappe.utils.escape_html(v == null ? "" : String(v));
    }

    // Exchange rate to company currency. Defaults to 1 for single-currency docs.
    function rate(r) {
        return flt(r.conversion_rate) || 1;
    }

    // outstanding_amount is denominated in PARTY ACCOUNT currency, which is NOT
    // necessarily the document currency -- see CORRECTNESS NOTE 3. Convert only
    // when the party account is genuinely foreign.
    function base_outstanding(r) {
        const o = flt(r.outstanding_amount);
        if (!o) return 0;

        const pac = r.party_account_currency;
        // No party_account_currency fetched (or the doctype has none) => the
        // figure is already in company currency. Converting would be the bug
        // this function exists to prevent, so the safe default is NOT to.
        if (!pac || pac === company_currency()) return o;

        return o * rate(r);
    }

    // The figure ERPNext actually settled against -- see CORRECTNESS NOTE 2.
    function base_payable(r) {
        return flt(r.base_rounded_total) || flt(r.base_grand_total);
    }

    // Collapse duplicate parent rows produced by a child-table JOIN.
    // A no-op when no child-table filter is active, since `name` is unique.
    function dedupe(rows) {
        const seen = new Set();
        return (rows || []).filter(function (d) {
            if (!d.name || seen.has(d.name)) return false;
            seen.add(d.name);
            return true;
        });
    }

    function days_overdue(due_date, outstanding) {
        if (flt(outstanding) <= 0 || !due_date) return 0;
        const due = frappe.datetime.str_to_obj(due_date);
        const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
        const diff = Math.floor((today - due) / 86400000);
        return diff > 0 ? diff : 0;
    }

    function ageing_bucket(days) {
        if (days <= 0) return "current";
        if (days <= 30) return "b1";
        if (days <= 60) return "b2";
        if (days <= 90) return "b3";
        return "b4";
    }

    function csv_cell(v) {
        v = v == null ? "" : String(v);
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    }

    function copy_text(text) {
        const done = function () {
            frappe.show_alert({ message: __("Copied"), indicator: "green" }, 2);
        };
        const fallback = function () {
            try {
                const ta = document.createElement("textarea");
                ta.value = text;
                ta.style.position = "fixed";
                ta.style.opacity = "0";
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                done();
            } catch (e) {
                frappe.show_alert({ message: __("Copy failed"), indicator: "red" }, 3);
            }
        };
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done).catch(fallback);
            } else {
                fallback();
            }
        } catch (e) {
            fallback();
        }
    }

    function download(text, filename, mime) {
        const blob = new Blob([text], { type: mime || "text/csv;charset=utf-8;" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
    }

    // =========================================================================
    // COLUMN FILTER ENGINE
    // -------------------------------------------------------------------------
    // Text columns  : case-insensitive substring.
    // Number columns: >n  >=n  <n  <=n  =n  n1-n2 (inclusive range)
    //                 a bare number falls back to substring on the raw digits,
    //                 so typing "500" still finds 1,500 and 500,000.
    // An empty box matches everything.
    // =========================================================================

    function make_predicate(expr, type) {
        expr = (expr || "").trim();
        if (!expr) return null;

        if (type === "num") {
            let m = expr.match(/^(>=|<=|>|<|=)\s*(-?[\d.,]+)$/);
            if (m) {
                const op = m[1];
                const n = flt(m[2].replace(/,/g, ""));
                return function (v) {
                    v = flt(v);
                    if (op === ">") return v > n;
                    if (op === "<") return v < n;
                    if (op === ">=") return v >= n;
                    if (op === "<=") return v <= n;
                    return v === n;
                };
            }
            m = expr.match(/^(-?[\d.,]+)\s*(?:-|\.\.)\s*(-?[\d.,]+)$/);
            if (m) {
                const lo = flt(m[1].replace(/,/g, ""));
                const hi = flt(m[2].replace(/,/g, ""));
                return function (v) { v = flt(v); return v >= lo && v <= hi; };
            }
            const needle = expr.toLowerCase();
            return function (v) { return String(flt(v)).toLowerCase().indexOf(needle) !== -1; };
        }

        const needle = expr.toLowerCase();
        return function (v) {
            return String(v == null ? "" : v).toLowerCase().indexOf(needle) !== -1;
        };
    }

    // =========================================================================
    // DOCTYPE CONFIGURATION
    // -------------------------------------------------------------------------
    // party   : how rows group in the Summary dialog
    // fields  : docfields fetched. "name" is added automatically.
    // metrics : display order. `get` sums per row; `calc` derives from the sums.
    //           `hidden: true` computes a value without showing it as a row.
    // summary : which metric keys become money columns in the Summary table.
    // ageing  : true adds the Overdue column and the receivables ageing block.
    // =========================================================================

    const MONEY_TXN = [
        "base_net_total", "base_total_taxes_and_charges",
        "base_grand_total", "base_rounded_total", "currency", "conversion_rate",
    ];

    const TXN_METRICS = [
        { key: "net",   label: "Net Total",   get: function (r) { return flt(r.base_net_total); } },
        { key: "tax",   label: "Tax / VAT",   get: function (r) { return flt(r.base_total_taxes_and_charges); } },
        { key: "grand", label: "Grand Total", get: function (r) { return flt(r.base_grand_total); } },
    ];

    // Metrics for anything carrying an outstanding balance.
    function payable_metrics() {
        return TXN_METRICS.concat([
            { key: "payable", hidden: true, get: base_payable },
            { key: "due",     label: "Outstanding", color: "red",   get: base_outstanding },
            { key: "paid",    label: "Paid",        color: "green",
              calc: function (s) { return s.payable - s.due; }, before: "due" },
        ]);
    }

    const CONFIG = {
        "Quotation": {
            route: "quotation", abbr: "QTN",
            party: { field: "party_name", name_field: "customer_name", label: "Customer / Lead" },
            summary_button: "Customer Summary", totals_button: "Quotation Totals",
            fields: ["party_name", "customer_name", "status", "project", "transaction_date"].concat(MONEY_TXN),
            metrics: TXN_METRICS,
            summary: ["net", "grand"],
        },

        "Sales Order": {
            route: "sales-order", abbr: "SO",
            party: { field: "customer", name_field: "customer_name", label: "Customer" },
            summary_button: "Customer Summary", totals_button: "Sales Order Totals",
            fields: ["customer", "customer_name", "status", "project", "transaction_date"].concat(MONEY_TXN),
            metrics: TXN_METRICS,
            summary: ["net", "grand"],
        },

        "Sales Invoice": {
            route: "sales-invoice", abbr: "SINV",
            party: { field: "customer", name_field: "customer_name", label: "Customer" },
            summary_button: "Customer Summary", totals_button: "Sales Totals",
            fields: ["customer", "customer_name", "status", "project",
                     "posting_date", "due_date", "outstanding_amount",
                     "party_account_currency"].concat(MONEY_TXN),
            metrics: payable_metrics(),
            summary: ["grand", "due"],
            ageing: true, ageing_label: "RECEIVABLES AGEING (outstanding)",
        },

        "Purchase Order": {
            route: "purchase-order", abbr: "PO",
            party: { field: "supplier", name_field: "supplier_name", label: "Supplier" },
            summary_button: "Supplier Summary", totals_button: "Purchase Order Totals",
            fields: ["supplier", "supplier_name", "status", "project", "transaction_date"].concat(MONEY_TXN),
            metrics: TXN_METRICS,
            summary: ["net", "grand"],
        },

        "Purchase Invoice": {
            route: "purchase-invoice", abbr: "PINV",
            party: { field: "supplier", name_field: "supplier_name", label: "Supplier" },
            summary_button: "Supplier Summary", totals_button: "Purchase Totals",
            fields: ["supplier", "supplier_name", "status", "project",
                     "posting_date", "due_date", "outstanding_amount",
                     "party_account_currency"].concat(MONEY_TXN),
            metrics: payable_metrics(),
            summary: ["grand", "due"],
            ageing: true, ageing_label: "PAYABLES AGEING (outstanding)",
        },

        "Payment Entry": {
            route: "payment-entry", abbr: "PE",
            party: { field: "party", name_field: "party_name", label: "Party" },
            summary_button: "Party Summary", totals_button: "Payment Entry Totals",
            fields: ["party", "party_name", "party_type", "payment_type", "status",
                     "project", "posting_date", "currency",
                     "base_paid_amount", "base_received_amount", "base_total_allocated_amount"],
            metrics: [
                { key: "paid_amt",  label: "Paid",      get: function (r) { return flt(r.base_paid_amount); } },
                { key: "recd_amt",  label: "Received",  get: function (r) { return flt(r.base_received_amount); } },
                { key: "allocated", label: "Allocated", color: "green",
                  get: function (r) { return flt(r.base_total_allocated_amount); } },
                // Payment Entry has NO base_unallocated_amount field, so this is
                // derived from base figures rather than read directly.
                { key: "unalloc",   label: "Unallocated", color: "red",
                  calc: function (s) { return s.paid_amt - s.allocated; } },
            ],
            summary: ["paid_amt", "allocated"],
            avg_key: "paid_amt",
        },

        "Expense Claim": {
            route: "expense-claim", abbr: "EXP",
            party: { field: "employee", name_field: "employee_name", label: "Employee" },
            summary_button: "Employee Summary", totals_button: "Expense Claim Totals",
            // Expense Claim is single-currency (company currency), no base_ fields.
            fields: ["employee", "employee_name", "status", "project", "posting_date",
                     "total_claimed_amount", "total_sanctioned_amount", "total_amount_reimbursed"],
            metrics: [
                { key: "claimed",    label: "Claimed",    get: function (r) { return flt(r.total_claimed_amount); } },
                { key: "sanctioned", label: "Sanctioned", get: function (r) { return flt(r.total_sanctioned_amount); } },
                { key: "reimbursed", label: "Reimbursed", color: "green",
                  get: function (r) { return flt(r.total_amount_reimbursed); } },
                { key: "due",        label: "Outstanding", color: "red",
                  calc: function (s) { return s.sanctioned - s.reimbursed; } },
            ],
            summary: ["sanctioned", "due"],
            avg_key: "sanctioned",
        },
    };

    // =========================================================================
    // DATA ACCESS
    // =========================================================================

    // -------------------------------------------------------------------------
    // PROJECT -> CUSTOMER
    // The invoice knows its Project; the end customer lives on Project.customer.
    // Resolved in one batched query per unseen project and cached for the whole
    // session, so reopening the dialog costs nothing. Projects that come back
    // empty (deleted, or no read permission) are cached as "" so they are not
    // re-queried on every open.
    // -------------------------------------------------------------------------
    const PROJECT_CUSTOMER = {};

    function load_project_customers(projects) {
        const missing = (projects || []).filter(function (p) {
            return p && !Object.prototype.hasOwnProperty.call(PROJECT_CUSTOMER, p);
        });
        if (!missing.length) return Promise.resolve(PROJECT_CUSTOMER);

        const CHUNK = 300;
        const batches = [];
        for (let i = 0; i < missing.length; i += CHUNK) {
            batches.push(missing.slice(i, i + CHUNK));
        }

        return Promise.all(batches.map(function (batch) {
            return new Promise(function (resolve) {
                const seal = function () {
                    batch.forEach(function (p) {
                        if (!Object.prototype.hasOwnProperty.call(PROJECT_CUSTOMER, p)) {
                            PROJECT_CUSTOMER[p] = "";
                        }
                    });
                    resolve();
                };
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Project",
                        fields: ["name", "customer"],
                        filters: [["Project", "name", "in", batch]],
                        limit_page_length: batch.length,
                    },
                    callback: function (r) {
                        (r.message || []).forEach(function (p) {
                            PROJECT_CUSTOMER[p.name] = p.customer || "";
                        });
                        seal();
                    },
                    error: function (e) {
                        // No read access to Project is not fatal -- the column
                        // just stays blank.
                        console.warn("[IAES listview utils] could not read Project customers", e);
                        seal();
                    },
                });
            });
        })).then(function () { return PROJECT_CUSTOMER; });
    }

    function current_filters(listview) {
        if (listview.get_filters_for_args) return listview.get_filters_for_args() || [];
        return (listview.filter_area && listview.filter_area.get()) || [];
    }

    // Drop any field the doctype does not actually have -- see CORRECTNESS NOTE 5.
    // Falls back to the full list if meta is unavailable, so a missing meta can
    // never make things worse than not filtering at all.
    const STANDARD_FIELDS = new Set([
        "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
    ]);

    function valid_fields(doctype, fields) {
        let meta = null;
        try { meta = frappe.get_meta(doctype); } catch (e) { meta = null; }
        if (!meta || !meta.fields || !meta.fields.length) return fields;

        const have = new Set(meta.fields.map(function (f) { return f.fieldname; }));
        const kept = fields.filter(function (f) { return STANDARD_FIELDS.has(f) || have.has(f); });
        const dropped = fields.filter(function (f) { return kept.indexOf(f) === -1; });
        if (dropped.length) {
            console.warn("[IAES listview utils]", doctype, "has no field(s):", dropped.join(", "),
                         "— excluded from the query.");
        }
        return kept;
    }

    // Resolves to { rows, scoped, truncated, currencies, fields }.
    // `scoped` means the user had rows ticked, so only those were totalled.
    function fetch_rows(listview, cfg, doctype) {
        const checked = (listview.get_checked_items ? listview.get_checked_items(true) : []) || [];
        const filters = checked.length
            ? [[doctype, "name", "in", checked]]
            : current_filters(listview);

        const fields = valid_fields(doctype, Array.from(new Set(["name"].concat(cfg.fields))));

        return new Promise(function (resolve, reject) {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: doctype,
                    fields: fields,
                    filters: filters,
                    limit_page_length: MAX_ROWS,
                },
                callback: function (r) {
                    const raw = r.message || [];
                    if (raw.length >= MAX_ROWS) {
                        frappe.show_alert({
                            message: __("Row limit of {0} reached — figures may be incomplete. Narrow the filter.", [MAX_ROWS]),
                            indicator: "orange",
                        }, 6);
                    }
                    const rows = dedupe(raw);   // CORRECTNESS NOTE 1

                    // The end customer lives on Project, not on the invoice, so
                    // it needs a second (cached) round trip before rendering.
                    const projects = Array.from(new Set(
                        rows.map(function (d) { return d.project; }).filter(Boolean)
                    ));

                    load_project_customers(projects).then(function (pmap) {
                        resolve({
                            rows: rows,
                            scoped: checked.length > 0,
                            truncated: raw.length >= MAX_ROWS,
                            currencies: Array.from(new Set(rows.map(function (d) { return d.currency; }).filter(Boolean))),
                            fields: fields,
                            project_customers: pmap,
                        });
                    });
                },
                error: function (err) {
                    // get_list rejects the whole request on one bad column, so
                    // say which doctype died instead of failing silently.
                    console.error("[IAES listview utils] fetch failed for", doctype, "fields:", fields, err);
                    reject(err);
                },
            });
        });
    }

    // Sum every `get` metric, then evaluate every `calc` metric.
    function aggregate(rows, cfg) {
        const sums = {};
        cfg.metrics.forEach(function (m) { sums[m.key] = 0; });
        rows.forEach(function (r) {
            cfg.metrics.forEach(function (m) {
                if (m.get) sums[m.key] += flt(m.get(r));
            });
        });
        cfg.metrics.forEach(function (m) {
            if (m.calc) sums[m.key] = flt(m.calc(sums));
        });
        return sums;
    }

    // Metrics in display order, with `before:` honoured and hidden ones dropped.
    function visible_metrics(cfg) {
        const out = [];
        cfg.metrics.forEach(function (m) {
            if (m.hidden) return;
            if (m.before) {
                const i = out.findIndex(function (x) { return x.key === m.before; });
                if (i !== -1) { out.splice(i, 0, m); return; }
            }
            out.push(m);
        });
        return out;
    }

    function group_by_party(rows, cfg, pmap) {
        pmap = pmap || {};
        const map = {};
        rows.forEach(function (r) {
            const key = r[cfg.party.field] || r[cfg.party.name_field] || "(blank)";
            if (!map[key]) {
                map[key] = {
                    party: r[cfg.party.name_field] || r[cfg.party.field] || "(blank)",
                    count: 0, docs: [], entries: [], projects: new Set(),
                    currencies: new Set(), project_customers: new Set(),
                    overdue: 0, sums: {},
                };
                cfg.metrics.forEach(function (m) { map[key].sums[m.key] = 0; });
            }
            const g = map[key];
            g.count += 1;
            g.docs.push(r.name);
            // Row-aligned triple: the doc, its project, and that project's
            // customer -- see CORRECTNESS NOTE 6.
            g.entries.push({
                name: r.name,
                project: r.project || "",
                customer: (r.project && pmap[r.project]) || "",
            });
            if (r.project) {
                g.projects.add(r.project);
                if (pmap[r.project]) g.project_customers.add(pmap[r.project]);
            }
            if (r.currency) g.currencies.add(r.currency);
            cfg.metrics.forEach(function (m) {
                if (m.get) g.sums[m.key] += flt(m.get(r));
            });
            if (cfg.ageing && days_overdue(r.due_date, base_outstanding(r)) > 0) {
                g.overdue += base_outstanding(r);
            }
        });
        return Object.values(map).map(function (g) {
            cfg.metrics.forEach(function (m) {
                if (m.calc) g.sums[m.key] = flt(m.calc(g.sums));
            });
            g.projects = Array.from(g.projects);
            g.currencies = Array.from(g.currencies).sort();
            g.project_customers = Array.from(g.project_customers).sort();
            return g;
        });
    }

    // =========================================================================
    // SUMMARY DIALOG
    // =========================================================================

    function show_summary(listview, cfg, doctype) {
        fetch_rows(listview, cfg, doctype).then(function (res) {
            if (!res.rows.length) {
                frappe.msgprint(__("No records found for the current filters."));
                return;
            }

            const groups = group_by_party(res.rows, cfg, res.project_customers || {});
            const money_keys = cfg.summary || [];
            const metric_by_key = {};
            cfg.metrics.forEach(function (m) { metric_by_key[m.key] = m; });

            // ---- column model -------------------------------------------------
            // Project(s) only exists where the doctype actually has the field --
            // see CORRECTNESS NOTE 5 (Quotation does not).
            const has_project  = (res.fields || []).indexOf("project")  !== -1;
            const has_currency = (res.fields || []).indexOf("currency") !== -1;

            const cols = [
                { label: "#", type: "none", align: "center", width: "36px" },
                { label: cfg.party.label, type: "text", get: function (g) { return g.party; } },
            ];

            // Document currency, between the party and the doc count. A party can
            // hold docs in several currencies, so this is the distinct set, not a
            // single value -- and it is a reminder that the money columns beside
            // it are converted to company currency, not raw document amounts.
            if (has_currency) {
                cols.push({
                    label: "Currency", type: "text", align: "center", width: "82px",
                    get: function (g) { return g.currencies.join(", "); },
                });
            }

            cols.push({ label: "Docs", type: "num", align: "center", sort: "count",
                        get: function (g) { return g.count; } });
            cols.push({ label: cfg.abbr + "(s)", type: "text",
                        get: function (g) {
                            return g.entries.map(function (e) { return e.name; }).join(" ");
                        } });

            if (has_project) {
                cols.push({ label: "Project(s)", type: "text",
                            get: function (g) {
                                return g.entries.map(function (e) { return e.project; })
                                                .filter(Boolean).join(" ");
                            } });

                // End customer, resolved from Project.customer. This is the
                // column to type into when you want "everything we billed for
                // customer X", which the invoice itself cannot answer.
                cols.push({ label: "Project Customer(s)", type: "text",
                            get: function (g) {
                                return g.entries.map(function (e) { return e.customer; })
                                                .filter(Boolean).join(" ");
                            } });
            }

            money_keys.forEach(function (k) {
                const m = metric_by_key[k];
                if (!m) return;
                cols.push({
                    label: m.label, type: "num", align: "right", money: true,
                    sort: k, color: m.color,
                    get: function (g) { return g.sums[k]; },
                });
            });

            if (cfg.ageing) {
                cols.push({
                    label: "Overdue", type: "num", align: "right", money: true,
                    sort: "overdue", color: "red",
                    get: function (g) { return g.overdue; },
                });
            }

            // ---- state --------------------------------------------------------
            let sort_state = { idx: null, dir: "desc" };
            const filters = cols.map(function () { return ""; });

            function passing() {
                const preds = cols.map(function (c, i) {
                    return c.type === "none" ? null : make_predicate(filters[i], c.type);
                });
                return groups.filter(function (g) {
                    for (let i = 0; i < cols.length; i++) {
                        if (!preds[i]) continue;
                        if (!preds[i](cols[i].get(g))) return false;
                    }
                    return true;
                });
            }

            function sorted(list) {
                if (sort_state.idx === null) {
                    return list.slice().sort(function (a, b) {
                        const k = money_keys[money_keys.length - 1];
                        return flt(b.sums[k]) - flt(a.sums[k]);
                    });
                }
                const c = cols[sort_state.idx];
                const mul = sort_state.dir === "asc" ? 1 : -1;
                return list.slice().sort(function (a, b) {
                    const av = c.get(a), bv = c.get(b);
                    if (c.type === "num") return (flt(av) - flt(bv)) * mul;
                    return String(av).localeCompare(String(bv)) * mul;
                });
            }

            // One line per document, always in the same order, so line N of
            // PINV(s), Project(s) and Project Customer(s) describe the SAME
            // invoice -- see CORRECTNESS NOTE 6. Lines are forced to a single
            // row of fixed height and ellipsised, because a wrapped line in one
            // column would push the columns out of step again. The full value
            // stays available on hover and in the CSV.
            const LINE_H = 19;

            function stacked(g, pick, route) {
                if (!g.entries.length) return '<span class="text-muted">—</span>';
                return g.entries.map(function (e) {
                    const val = pick(e);
                    const body = val
                        ? '<a href="/app/' + route + "/" + encodeURIComponent(val) +
                          '" target="_blank">' + esc(val) + "</a>"
                        : '<span class="text-muted">—</span>';
                    return '<div title="' + esc(val || "") + '" style="height:' + LINE_H +
                           "px;line-height:" + LINE_H +
                           'px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' +
                           body + "</div>";
                }).join("");
            }

            function cell_html(c, g) {
                const v = c.get(g);
                if (c.money) {
                    const style = c.color === "red" && flt(v) > 0 ? ' style="color:#c0392b;font-weight:600"' : "";
                    return "<span" + style + ">" + money(v) + "</span>";
                }
                if (c.label === cfg.abbr + "(s)") {
                    return stacked(g, function (e) { return e.name; }, cfg.route);
                }
                if (c.label === "Currency") {
                    return g.currencies.length
                        ? g.currencies.map(function (x) { return esc(x); }).join(", ")
                        : '<span class="text-muted">—</span>';
                }
                if (c.label === "Project Customer(s)") {
                    return stacked(g, function (e) { return e.customer; }, "customer");
                }
                if (c.label === "Project(s)") {
                    return stacked(g, function (e) { return e.project; }, "project");
                }
                return esc(v);
            }

            function body_html(list) {
                if (!list.length) {
                    return '<tr><td colspan="' + cols.length +
                           '" style="text-align:center;padding:18px;color:#999">' +
                           __("No rows match these column filters") + "</td></tr>";
                }
                return list.map(function (g, i) {
                    let tds = '<td style="text-align:center">' + (i + 1) + "</td>";
                    for (let ci = 1; ci < cols.length; ci++) {
                        const c = cols[ci];
                        tds += '<td style="text-align:' + (c.align || "left") +
                               (c.type === "text" && ci > 1 ? ";font-size:11px;word-break:break-word" : "") +
                               '">' + cell_html(c, g) + "</td>";
                    }
                    return "<tr>" + tds + "</tr>";
                }).join("");
            }

            function foot_html(list) {
                const tot = { count: 0, overdue: 0, sums: {} };
                cfg.metrics.forEach(function (m) { tot.sums[m.key] = 0; });
                list.forEach(function (g) {
                    tot.count += g.count;
                    tot.overdue += g.overdue;
                    cfg.metrics.forEach(function (m) { tot.sums[m.key] += flt(g.sums[m.key]); });
                });

                // Built by walking `cols` rather than by fixed offsets, so an
                // absent Project(s) column cannot shift the money cells.
                let tds = "";
                cols.forEach(function (c, i) {
                    if (i === 0) {
                        tds += "<td></td>";
                    } else if (i === 1) {
                        tds += "<td>" + __("TOTAL") + " (" + list.length + " " +
                               cfg.party.label.toLowerCase() + (list.length === 1 ? "" : "s") + ")</td>";
                    } else if (c.sort === "count") {
                        tds += '<td style="text-align:center">' + tot.count + "</td>";
                    } else if (c.sort === "overdue") {
                        tds += '<td style="text-align:right;color:#c0392b">' + money(tot.overdue) + "</td>";
                    } else if (c.money) {
                        tds += '<td style="text-align:right">' + money(tot.sums[c.sort]) + "</td>";
                    } else {
                        tds += "<td></td>";
                    }
                });
                return '<tr style="font-weight:700;background:#f5f5f5;border-top:2px solid #ccc">' + tds + "</tr>";
            }

            // ---- markup -------------------------------------------------------
            const head_cells = cols.map(function (c, i) {
                const sortable = !!c.sort || c.type === "text";
                return '<th data-col="' + i + '" style="text-align:' + (c.align || "left") +
                       (sortable ? ";cursor:pointer" : "") +
                       (c.width ? ";width:" + c.width : "") + '">' + esc(c.label) +
                       (sortable ? ' <span style="opacity:.35">⇅</span>' : "") + "</th>";
            }).join("");

            const filter_cells = cols.map(function (c, i) {
                if (c.type === "none") return "<th></th>";
                const ph = c.type === "num" ? ">1000" : __("filter…");
                return '<th style="padding:2px 4px"><input type="text" class="form-control input-xs iaes-colf" ' +
                       'data-col="' + i + '" placeholder="' + ph +
                       '" style="font-size:11px;height:24px;padding:2px 6px;font-weight:400"></th>';
            }).join("");

            const mixed = res.currencies.length > 1
                ? '<div style="margin-bottom:8px;padding:6px 10px;border-radius:4px;background:#fff8e1;font-size:12px">' +
                  "<b>" + __("Mixed currencies") + ":</b> " + esc(res.currencies.join(", ")) + " — " +
                  __("figures are converted to {0} using each document's exchange rate.", [company_currency()]) +
                  "</div>"
                : "";

            const html =
                mixed +
                '<div style="margin-bottom:6px;display:flex;gap:10px;align-items:center;font-size:12px;color:#777">' +
                    '<span class="iaes-count" style="font-weight:600;color:#555"></span>' +
                    "<span>" + __("Number columns accept") + " <code>&gt;1000000</code>, <code>&lt;500</code>, <code>100-5000</code></span>" +
                    (res.scoped ? '<span style="color:#2980b9">' + __("Selected rows only") + "</span>" : "") +
                    '<a href="#" class="iaes-clearf" style="margin-left:auto">' + __("Clear filters") + "</a>" +
                "</div>" +
                '<div style="max-height:58vh;overflow:auto;border:1px solid #e0e0e0;border-radius:6px">' +
                '<table class="table table-bordered" style="margin:0;font-size:13px">' +
                    '<thead style="position:sticky;top:0;background:#fafafa;z-index:1">' +
                        "<tr>" + head_cells + "</tr>" +
                        '<tr class="iaes-filter-row">' + filter_cells + "</tr>" +
                    "</thead>" +
                    '<tbody class="iaes-body">' + body_html(sorted(groups)) + "</tbody>" +
                    '<tfoot class="iaes-foot">' + foot_html(groups) + "</tfoot>" +
                "</table></div>";

            const d = new frappe.ui.Dialog({
                title: __("{0} ({1} records)", [cfg.summary_button, res.rows.length]),
                size: "extra-large",
                fields: [{ fieldtype: "HTML", fieldname: "area", options: html }],
                primary_action_label: __("Refresh"),
                primary_action: function () { d.hide(); show_summary(listview, cfg, doctype); },
            });

            d.show();
            const $w = d.$wrapper;

            function repaint() {
                const list = sorted(passing());
                $w.find(".iaes-body").html(body_html(list));
                $w.find(".iaes-foot").html(foot_html(list));

                // Visible-vs-total count, so a filtered footer is never mistaken
                // for the full picture.
                const label = cfg.party.label.toLowerCase() + (groups.length === 1 ? "" : "s");
                $w.find(".iaes-count").text(
                    list.length === groups.length
                        ? __("{0} {1}", [groups.length, label])
                        : __("Showing {0} of {1} {2}", [list.length, groups.length, label])
                ).css("color", list.length === groups.length ? "#555" : "#2980b9");
            }

            repaint();   // paint the count on open

            $w.on("input", ".iaes-colf", function () {
                filters[parseInt($(this).data("col"), 10)] = this.value;
                repaint();
            });

            $w.on("click", ".iaes-clearf", function (e) {
                e.preventDefault();
                for (let i = 0; i < filters.length; i++) filters[i] = "";
                $w.find(".iaes-colf").val("");
                repaint();
            });

            $w.on("click", "thead th[data-col]", function (e) {
                if ($(e.target).is("input")) return;      // clicking a filter box must not sort
                const i = parseInt($(this).data("col"), 10);
                const c = cols[i];
                if (!c.sort && c.type !== "text") return;
                sort_state = {
                    idx: i,
                    dir: sort_state.idx === i && sort_state.dir === "desc" ? "asc" : "desc",
                };
                repaint();
            });

            // ---- CSV ----------------------------------------------------------
            function build_csv() {
                const list = sorted(passing());
                const lines = [cols.map(function (c) { return c.label; }).map(csv_cell).join(",")];
                list.forEach(function (g, i) {
                    const cells = [i + 1];
                    for (let ci = 1; ci < cols.length; ci++) {
                        const c = cols[ci];
                        const v = c.get(g);
                        cells.push(c.money ? flt(v).toFixed(2) : v);
                    }
                    lines.push(cells.map(csv_cell).join(","));
                });
                return lines.join("\n");
            }

            d.set_secondary_action_label(__("Copy CSV"));
            d.set_secondary_action(function () { copy_text(build_csv()); });

            const $dl = $('<button class="btn btn-default btn-sm" style="margin-left:8px">' +
                          __("Download CSV") + "</button>");
            $dl.on("click", function () {
                download(build_csv(), cfg.abbr + "_Summary_" + frappe.datetime.get_today() + ".csv");
            });
            $w.find(".modal-footer .btn-modal-secondary").after($dl);
        });
    }

    // =========================================================================
    // TOTALS PANEL
    // =========================================================================

    const PANEL_ID = "iaes-totals-panel";
    let last_pos = null;

    function show_totals(listview, cfg, doctype) {
        $("#" + PANEL_ID).remove();

        fetch_rows(listview, cfg, doctype).then(function (res) {
            const rows = res.rows;
            const sums = aggregate(rows, cfg);
            const n = rows.length;

            const avg_key = cfg.avg_key || "grand";
            const avg = n ? flt(sums[avg_key]) / n : 0;

            const parties = new Set();
            rows.forEach(function (r) {
                const p = r[cfg.party.field] || r[cfg.party.name_field];
                if (p) parties.add(p);
            });

            const status = {};
            rows.forEach(function (r) { if (r.status) status[r.status] = (status[r.status] || 0) + 1; });

            // Every figure is individually click-to-copy. `raw` is what lands on
            // the clipboard -- the plain number, not the formatted string, so it
            // pastes straight into a spreadsheet cell.
            const line = function (label, val, color, raw) {
                const copyable = raw != null;
                return '<tr><td style="padding:3px 0;color:#555">' + esc(label) + "</td>" +
                       '<td class="' + (copyable ? "iaes-val" : "") + '"' +
                       (copyable ? ' data-copy="' + esc(raw) + '" title="' + __("Click to copy") + '"' : "") +
                       ' style="padding:3px 0;text-align:right;font-weight:600' +
                       (copyable ? ";cursor:pointer" : "") +
                       (color ? ";color:" + color : "") + '">' + val +
                       (copyable ? ' <span style="opacity:.3;font-size:11px;font-weight:400">&#10697;</span>' : "") +
                       "</td></tr>";
            };

            let metric_html = "";
            visible_metrics(cfg).forEach(function (m) {
                const c = m.color === "red" ? "#c0392b" : m.color === "green" ? "#27ae60" : "";
                metric_html += line(m.label + ":", money(sums[m.key]), c, flt(sums[m.key]).toFixed(2));
            });

            // Outstanding % only means something where a payable base exists.
            let pct_html = "";
            if (sums.payable !== undefined && flt(sums.payable)) {
                const p = (flt(sums.due) / flt(sums.payable) * 100).toFixed(1);
                pct_html = line(__("Outstanding %") + ":", p + "%", "", p);
            } else if (sums.sanctioned !== undefined && flt(sums.sanctioned)) {
                const p = (flt(sums.due) / flt(sums.sanctioned) * 100).toFixed(1);
                pct_html = line(__("Outstanding %") + ":", p + "%", "", p);
            }

            let ageing_html = "";
            if (cfg.ageing) {
                const ag = { current: 0, b1: 0, b2: 0, b3: 0, b4: 0 };
                rows.forEach(function (r) {
                    const o = base_outstanding(r);
                    ag[ageing_bucket(days_overdue(r.due_date, o))] += o;
                });
                const arow = function (label, v, c) {
                    return '<tr><td style="padding:2px 0;color:#666;font-size:12px">' + label + "</td>" +
                           '<td class="iaes-val" data-copy="' + esc(flt(v).toFixed(2)) +
                           '" title="' + __("Click to copy") + '"' +
                           ' style="padding:2px 0;text-align:right;font-size:12px;cursor:pointer' +
                           (c ? ";color:" + c : "") + '">' + money(v) + "</td></tr>";
                };
                ageing_html =
                    '<hr style="margin:8px 0"><div style="font-size:11px;color:#888;margin-bottom:4px">' +
                    esc(cfg.ageing_label || "AGEING") + "</div><table style=\"width:100%\">" +
                    arow(__("Not yet due"), ag.current, "#16a085") +
                    arow("1–30 " + __("days"), ag.b1) +
                    arow("31–60 " + __("days"), ag.b2, "#e67e22") +
                    arow("61–90 " + __("days"), ag.b3, "#d35400") +
                    arow("90+ " + __("days"), ag.b4, "#c0392b") +
                    "</table>";
            }

            const chips = Object.keys(status).sort().map(function (s) {
                return '<span style="display:inline-block;background:#eef;border-radius:10px;' +
                       'padding:1px 8px;margin:2px;font-size:11px">' + esc(s) + ": " + status[s] + "</span>";
            }).join("");

            const mixed = res.currencies.length > 1
                ? '<div style="padding:5px 8px;margin-bottom:8px;border-radius:4px;background:#fff8e1;font-size:11px">' +
                  "<b>" + __("Mixed currencies") + ":</b> " + esc(res.currencies.join(", ")) +
                  " → " + esc(company_currency()) + "</div>"
                : "";

            const pos = last_pos
                ? "left:" + last_pos.left + "px;top:" + last_pos.top + "px;"
                : "left:24px;top:120px;";

            $("body").append(
                '<div id="' + PANEL_ID + '" style="position:fixed;' + pos + "z-index:1050;width:330px;" +
                "background:#fff;border:1px solid #ddd;border-radius:10px;" +
                'box-shadow:0 6px 24px rgba(0,0,0,.18);padding:14px 16px;font-size:13px">' +
                    '<div class="iaes-drag" style="display:flex;justify-content:space-between;' +
                        'align-items:center;margin-bottom:6px;cursor:move">' +
                        "<b>" + esc(cfg.totals_button) + "</b>" +
                        '<span class="iaes-close" style="cursor:pointer;font-size:18px;line-height:1">&times;</span>' +
                    "</div>" +
                    '<div style="color:#777;font-size:12px;margin-bottom:8px">' +
                        n + " " + __("records") + (res.scoped ? " (" + __("selected") + ")" : " " + __("in current filter")) +
                        " · " + parties.size + " " + esc(cfg.party.label.toLowerCase()) + (parties.size === 1 ? "" : "s") +
                    "</div>" +
                    mixed +
                    '<table style="width:100%">' + metric_html + "</table>" +
                    '<hr style="margin:8px 0"><table style="width:100%">' +
                        line(__("Avg / record") + ":", money(avg), "", flt(avg).toFixed(2)) + pct_html +
                    "</table>" +
                    ageing_html +
                    (chips ? '<hr style="margin:8px 0"><div>' + chips + "</div>" : "") +
                    '<div style="margin-top:10px;text-align:right">' +
                        '<a href="#" class="iaes-copy" style="margin-right:12px">' + __("Copy all") + "</a>" +
                        '<a href="#" class="iaes-refresh">' + __("Refresh") + "</a>" +
                    "</div>" +
                "</div>"
            );

            const $p = $("#" + PANEL_ID);

            $p.find(".iaes-close").on("click", function () { $p.remove(); });

            // Per-figure copy. Delegated, so it also covers the ageing rows.
            $p.on("click", ".iaes-val", function () {
                copy_text($(this).data("copy") + "");
            });
            $p.find(".iaes-refresh").on("click", function (e) {
                e.preventDefault();
                show_totals(current_listview(doctype) || listview, cfg, doctype);
            });
            $p.find(".iaes-copy").on("click", function (e) {
                e.preventDefault();
                const lines = [cfg.totals_button + " — " + n + " records"];
                visible_metrics(cfg).forEach(function (m) {
                    lines.push(m.label + ": " + money(sums[m.key]));
                });
                lines.push("Avg / record: " + money(avg));
                copy_text(lines.join("\n"));
            });

            $p.find(".iaes-drag").on("mousedown", function (e) {
                if ($(e.target).hasClass("iaes-close")) return;
                const ox = e.clientX - $p[0].offsetLeft;
                const oy = e.clientY - $p[0].offsetTop;
                e.preventDefault();
                $(document).on("mousemove.iaes", function (ev) {
                    const left = Math.max(4, Math.min(ev.clientX - ox, window.innerWidth - $p.outerWidth() - 4));
                    const top = Math.max(4, Math.min(ev.clientY - oy, window.innerHeight - 40));
                    $p.css({ left: left + "px", top: top + "px" });
                    last_pos = { left: left, top: top };
                }).on("mouseup.iaes", function () {
                    $(document).off("mousemove.iaes mouseup.iaes");
                });
            });
        });
    }

    // =========================================================================
    // WIRING
    // -------------------------------------------------------------------------
    // See CORRECTNESS NOTE 4. Two independent registration paths, one shared
    // idempotency flag. Whichever fires first wins; the other becomes a no-op.
    // =========================================================================

    function current_listview(doctype) {
        return (typeof cur_list !== "undefined" && cur_list && cur_list.doctype === doctype)
            ? cur_list : null;
    }

    // Attach the two inner buttons to a live ListView.
    // Returns true if the listview is now wired (or already was), false if the
    // listview is not ready yet and the caller should retry.
    function add_buttons(listview, doctype) {
        const cfg = CONFIG[doctype];
        if (!cfg) return true;                          // nothing to do for this doctype
        if (!listview || !listview.page) return false;  // not ready yet
        if (listview.__iaes_utils_wired) return true;   // already wired
        listview.__iaes_utils_wired = true;

        listview.page.add_inner_button(__(cfg.summary_button), function () {
            show_summary(current_listview(doctype) || listview, cfg, doctype);
        });
        listview.page.add_inner_button(__(cfg.totals_button), function () {
            const $p = $("#" + PANEL_ID);
            if ($p.length && $p.is(":visible")) { $p.remove(); return; }
            show_totals(current_listview(doctype) || listview, cfg, doctype);
        });
        return true;
    }

    // ---- PATH 1: frappe.listview_settings.onload ----------------------------
    // MERGE, never assign. ERPNext ships its own *_list.js with add_fields and
    // get_indicator; a bare assignment discards them (that was a real bug in
    // CustomScript0004). Note this merge only survives if no app assigns the
    // slot afterwards -- HRMS does exactly that for Expense Claim, which is why
    // PATH 2 exists.
    Object.keys(CONFIG).forEach(function (doctype) {
        frappe.listview_settings = frappe.listview_settings || {};
        const settings = frappe.listview_settings[doctype] || {};
        const prev_onload = settings.onload;

        settings.onload = function (listview) {
            // A foreign onload must never be able to take our buttons down
            // with it, so it runs inside its own guard.
            if (prev_onload) {
                try {
                    prev_onload(listview);
                } catch (e) {
                    console.error("[IAES listview utils] foreign onload failed for", doctype, e);
                }
            }
            add_buttons(listview, doctype);
        };

        frappe.listview_settings[doctype] = settings;
    });

    // ---- PATH 2: direct wiring off the live ListView ------------------------
    // Immune to listview_settings being reassigned by any other app. Polls
    // briefly because the ListView instance is created asynchronously after the
    // route changes.
    function wire_route(tries) {
        const route = frappe.get_route() || [];
        if (route[0] !== "List") return;

        const doctype = route[1];
        if (!CONFIG[doctype]) return;
        if (add_buttons(current_listview(doctype), doctype)) return;

        if ((tries || 0) < 40) {   // ~6s ceiling, then give up quietly
            setTimeout(function () { wire_route((tries || 0) + 1); }, 150);
        }
    }

    // Hide a stale panel when leaving the list view it belongs to,
    // and wire the buttons when entering a configured one.
    frappe.router.on("change", function () {
        const route = frappe.get_route() || [];
        if (route[0] !== "List" || !CONFIG[route[1]]) $("#" + PANEL_ID).remove();
        wire_route(0);
    });

    // First page load: the router "change" event may already have fired by the
    // time this file executes, so cover the initial route explicitly.
    if (frappe.after_ajax) {
        frappe.after_ajax(function () { wire_route(0); });
    } else {
        $(document).ready(function () { wire_route(0); });
    }

    return {
        CONFIG: CONFIG,
        show_summary: show_summary,
        show_totals: show_totals,
        _internals: { dedupe: dedupe, make_predicate: make_predicate, aggregate: aggregate,
                      group_by_party: group_by_party, visible_metrics: visible_metrics,
                      add_buttons: add_buttons, wire_route: wire_route },
    };

})();