// NMB Zone Monthly Billing – client-side report definition
// Path: iaes_custom/iaes_custom/report/nmb_zone_monthly_billing/nmb_zone_monthly_billing.js

frappe.query_reports["NMB Zone Monthly Billing"] = {

    // ── Filters ──────────────────────────────────────────────────────────────
    filters: [
        {
            fieldname: "project",
            label:     __("Project"),
            fieldtype: "Link",
            options:   "Project",
            default:   "NMB - Provision of Corrective Electrical Services the Southern and Central Zones",
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
            fieldname: "zone",
            label:     __("Zone"),
            fieldtype: "Select",
            options:   ["", "Central Zone", "Southern Zone", "Western Zone"],
        },
    ],

    // ── Row formatter ────────────────────────────────────────────────────────
    // Colours map to invoice structure so it reads like the physical costing sheet.
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data || !data.row_type) return value;

        const type = data.row_type;

        // Section headers  (e.g. "── SECTION 1: CALL OUT CHARGES ──")
        if (type === "section_header") {
            return `<span style="font-weight:700;color:#1a3a5c;letter-spacing:.5px;">${value}</span>`;
        }

        // Per-branch sub-headings
        if (type === "branch_header") {
            return `<span style="font-weight:600;color:#2c5f8a;text-decoration:underline;">${value}</span>`;
        }

        // Subtotal rows – highlight the Amount column only
        const subtotalTypes = [
            "subtotal_1_–_call_out_charges",
            "subtotal_2_–_parts_replacements",
            "subtotal_3",
        ];
        if (subtotalTypes.some(t => type.includes(t))) {
            if (column.fieldname === "amount" || column.fieldname === "branch_name") {
                return `<strong style="color:#155724;">${value}</strong>`;
            }
        }

        if (type.includes("vat_18%")) {
            if (column.fieldname === "amount" || column.fieldname === "branch_name") {
                return `<em>${value}</em>`;
            }
        }

        if (type.includes("grand_total")) {
            if (column.fieldname === "amount" || column.fieldname === "branch_name") {
                return `<strong style="font-size:1.05em;color:#004085;background:#cce5ff;padding:2px 6px;border-radius:3px;">${value}</strong>`;
            }
        }

        // Branch sub-subtotals
        if (type.startsWith("sub_total_–")) {
            return `<span style="font-style:italic;color:#555;">${value}</span>`;
        }

        // Attachment column: flag missing reports in red
        if (column.fieldname === "attachment" && type === "detail") {
            if (value === "None" || value === "") {
                return `<span style="color:#c0392b;font-weight:600;"
                        title="No job report attached">&#9888; None</span>`;
            }
            return `<span style="color:#27ae60;font-weight:600;"
                    title="${value}">&#10003; ${value}</span>`;
        }

        // Assigned To: grey if unassigned
        if (column.fieldname === "assigned_to" && type === "detail") {
            if (!value || value === "Unassigned") {
                return `<span style="color:#999;font-style:italic;">Unassigned</span>`;
            }
        }

        // Source Doc: clickable link to Expense Claim or Purchase Invoice
        if (column.fieldname === "source_doc" && type === "detail") {
            if (!value) return "";
            const parts  = value.split(":");
            if (parts.length < 2) return value;
            const doctype = parts[0];
            const docname = parts.slice(1).join(":");
            const route   = `/app/${doctype.toLowerCase().replace(/ /g, "-")}/${docname}`;
            const icon    = doctype === "Expense Claim" ? "\u{1F4CB}" : "\u{1F9FE}";
            const color   = doctype === "Expense Claim" ? "#1a6b3a" : "#1a3a6b";
            return `<a href="${route}" target="_blank"
                       style="color:${color};font-weight:600;text-decoration:none;font-size:11px;">
                       ${icon} ${docname}</a>`;
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
                __("Create a draft Sales Invoice for NMB Bank from this billing period?"),
                function () {
                    frappe.call({
                        method: "iaes_custom.iaes_custom.report.nmb_zone_monthly_billing"
                               + ".nmb_zone_monthly_billing.create_sales_invoice",
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