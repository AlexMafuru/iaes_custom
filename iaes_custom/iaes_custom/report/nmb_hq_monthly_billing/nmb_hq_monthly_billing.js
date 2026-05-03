// NMB HQ Monthly Billing – client-side report definition
// Path: iaes_custom/iaes_custom/report/nmb_hq_monthly_billing/nmb_hq_monthly_billing.js
//
// Tracks the HQ procurement-to-invoicing flow:
//   Material Request (MREQ) → Delivery Note (Dnote) → Purchase Invoice (PINV)
//   → Sales Invoice (SINV) to NMB Bank.

frappe.query_reports["NMB HQ Monthly Billing"] = {

    // ── Filters ──────────────────────────────────────────────────────────────
    filters: [
        {
            fieldname: "project",
            label:     __("Project"),
            fieldtype: "Link",
            options:   "Project",
            default:   "",  // TODO: set to the HQ project's full name (e.g. linked to PROJ-210)
            reqd:      1,
        },
        {
            fieldname: "from_date",
            label:     __("From Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_start(),
            reqd:      1,
        },
        {
            fieldname: "to_date",
            label:     __("To Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_end(),
            reqd:      1,
        },
        {
            fieldname: "scope",
            label:     __("Scope"),
            fieldtype: "Select",
            options:   ["", "AC", "Electrical", "Plumbing", "Generator", "Store"],
        },
        {
            fieldname: "hq_or_zone",
            label:     __("HQ / Dar Zone"),
            fieldtype: "Select",
            options:   ["", "HQ", "Dar Zone"],
        },
        {
            fieldname: "show_unbilled_only",
            label:     __("Show Unbilled Only"),
            fieldtype: "Check",
            default:   0,
        },
        {
            fieldname: "markup_percent",
            label:     __("Markup % (for SINV preview)"),
            fieldtype: "Float",
            default:   0,
        },
    ],

    // ── Row formatter ────────────────────────────────────────────────────────
    // Same row_type vocabulary as the Zone report so styling stays consistent.
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data || !data.row_type) return value;

        const type = data.row_type;

        // Top section banner — e.g. "── MATERIALS BY SCOPE ──"
        if (type === "section_header") {
            return `<span style="font-weight:700;color:#1a3a5c;letter-spacing:.5px;">${value}</span>`;
        }

        // Per-scope sub-heading — e.g. "AC", "Plumbing"
        if (type === "scope_header") {
            return `<span style="font-weight:600;color:#2c5f8a;text-decoration:underline;">${value}</span>`;
        }

        // Per-scope subtotals
        if (type === "subtotal_scope") {
            if (column.fieldname === "amount" || column.fieldname === "description") {
                return `<span style="font-style:italic;color:#555;font-weight:600;">${value}</span>`;
            }
        }

        // Materials grand subtotal
        if (type === "subtotal_materials") {
            if (column.fieldname === "amount" || column.fieldname === "description") {
                return `<strong style="color:#155724;">${value}</strong>`;
            }
        }

        // VAT row
        if (type === "vat_18%") {
            if (column.fieldname === "amount" || column.fieldname === "description") {
                return `<em>${value}</em>`;
            }
        }

        // Final grand total
        if (type === "grand_total") {
            if (column.fieldname === "amount" || column.fieldname === "description") {
                return `<strong style="font-size:1.05em;color:#004085;background:#cce5ff;padding:2px 6px;border-radius:3px;">${value}</strong>`;
            }
        }

        // ── Detail-row decorations ────────────────────────────────────────────
        if (type === "detail") {

            // Balance: red if positive (undelivered), grey if zero
            if (column.fieldname === "balance") {
                const num = parseFloat(data.balance);
                if (!isNaN(num) && num > 0) {
                    return `<span style="color:#c0392b;font-weight:600;" title="Undelivered">&#9888; ${value}</span>`;
                }
                if (!isNaN(num) && num === 0) {
                    return `<span style="color:#999;">${value}</span>`;
                }
            }

            // SINV: red flag if missing (= unbilled)
            if (column.fieldname === "sinv") {
                if (!value || value === "" || value === "None") {
                    return `<span style="color:#c0392b;font-weight:600;" title="Not yet billed to NMB">&#9888; Unbilled</span>`;
                }
            }

            // Dnote: warn if missing
            if (column.fieldname === "dnote") {
                if (!value || value === "" || value === "None") {
                    return `<span style="color:#e67e22;font-style:italic;" title="No delivery note">&#9888; None</span>`;
                }
            }

            // PINV: warn if missing (not yet purchased via PO/PINV path)
            if (column.fieldname === "pinv") {
                if (!value || value === "" || value === "None") {
                    return `<span style="color:#999;font-style:italic;">—</span>`;
                }
                return `<span style="color:#1a3a6b;font-weight:600;" title="Purchase Invoice path">&#129534; ${value}</span>`;
            }

            // EXP: warn if missing (not via expense-claim path)
            if (column.fieldname === "exp") {
                if (!value || value === "" || value === "None") {
                    return `<span style="color:#999;font-style:italic;">—</span>`;
                }
                return `<span style="color:#1a6b3a;font-weight:600;" title="Expense Claim path">&#128203; ${value}</span>`;
            }

            // Scope: small colored chip
            if (column.fieldname === "scope" && value) {
                const palette = {
                    "AC":         "#3498db",
                    "Electrical": "#f39c12",
                    "Plumbing":   "#16a085",
                    "Generator":  "#8e44ad",
                    "Store":      "#7f8c8d",
                };
                const color = palette[value] || "#555";
                return `<span style="background:${color};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px;">${value}</span>`;
            }

            // HQ/Zone: small chip
            if (column.fieldname === "hq_or_zone" && value) {
                const bg = value === "HQ" ? "#1a3a5c" : "#2c5f8a";
                return `<span style="background:${bg};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px;">${value}</span>`;
            }
        }

        return value;
    },

    // ── Toolbar buttons ──────────────────────────────────────────────────────
    onload: function (report) {

        // Export to Excel (built-in Frappe)
        report.page.add_inner_button(__("Export to Excel"), function () {
            frappe.query_report.export_report("Excel");
        }, __("Actions"));

        // Create a draft Sales Invoice from the current report
        report.page.add_inner_button(__("Create Sales Invoice"), function () {
            const filters = frappe.query_report.get_filter_values();
            if (!filters.project || !filters.from_date || !filters.to_date) {
                frappe.msgprint(__("Please set Project, From Date and To Date first."));
                return;
            }
            frappe.confirm(
                __("Create a draft Sales Invoice for NMB Bank HQ from this billing period?"),
                function () {
                    frappe.call({
                        method: "iaes_custom.iaes_custom.report.nmb_hq_monthly_billing"
                               + ".nmb_hq_monthly_billing.create_sales_invoice",
                        args:  { filters },
                        freeze: true,
                        freeze_message: __("Building Sales Invoice…"),
                        callback: function (r) {
                            if (r.message) {
                                frappe.show_alert({
                                    message: __("Invoice {0} created.", [
                                        `<a href='/app/sales-invoice/${r.message}'>${r.message}</a>`
                                    ]),
                                    indicator: "green",
                                }, 8);
                            }
                        },
                    });
                }
            );
        }, __("Actions"));

        // Shortcut: open the project record
        report.page.add_inner_button(__("Open Project"), function () {
            const proj = frappe.query_report.get_filter_value("project");
            if (proj) frappe.set_route("Form", "Project", proj);
        }, __("Actions"));
    },
};
