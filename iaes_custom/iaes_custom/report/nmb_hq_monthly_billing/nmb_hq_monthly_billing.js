// NMB HQ Monthly Billing — Client-side report UI
// =================================================
//
// Filters, row coloring by status, inline edit on Final Price,
// "Generate Quotation" button.

frappe.query_reports["NMB HQ Monthly Billing"] = {
    filters: [
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project",
            reqd: 1,
            default: "PROJ-0210",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.month_start(),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.month_end(),
        },
        {
            fieldname: "scope",
            label: __("Scope"),
            fieldtype: "Select",
            options: ["", "AC", "Electrical", "Plumbing", "Generator", "Kitchen", "Motor Rewinding", "AMC", "Store"],
        },
        {
            fieldname: "hq_or_zone",
            label: __("HQ / Dar Zone"),
            fieldtype: "Select",
            options: ["", "HQ", "Dar Zone"],
        },
        {
            fieldname: "approved_requisition_no",
            label: __("Approved Requisition No."),
            fieldtype: "Data",
        },
        {
            fieldname: "hide_quoted",
            label: __("Hide already-quoted lines"),
            fieldtype: "Check",
            default: 0,
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // Row coloring by status
        const status_colors = {
            "Ready to quote":  "#d4edda",  // green
            "DN missing":      "#fff3cd",  // amber
            "Not yet paid":    "#fff3cd",  // amber
            "No cost source":  "#f8d7da",  // red
            "Quoted":          "#e2e3e5",  // gray
        };

        const color = status_colors[data.status];
        if (color) {
            value = `<span style="display:block; padding:2px 4px; background:${color};">${value}</span>`;
        }

        // Highlight the Final Price column to signal it's editable
        if (column.fieldname === "final_price" && data.status !== "Quoted") {
            value = `<span style="font-weight:600; cursor:pointer; border-bottom:1px dashed #888;" title="Click to edit">${value}</span>`;
        }

        return value;
    },

    onload: function (report) {
        // "Generate Quotation" button
        report.page.add_inner_button(__("Generate Quotation"), function () {
            generate_quotation(report);
        }).addClass("btn-primary");

        // "Refresh Pricing" — recomputes prices without touching overrides
        report.page.add_inner_button(__("Refresh Pricing"), function () {
            report.refresh();
        });

        // Hook inline editing on Final Price
        setTimeout(() => attach_inline_edit(report), 800);
    },

    after_datatable_render: function (datatable) {
        // Re-attach inline edit after each render
        const report = frappe.query_report;
        if (report) attach_inline_edit(report);
    },
};


// ---------------------------------------------------------------------------
// Inline edit on Final Price column
// ---------------------------------------------------------------------------
function attach_inline_edit(report) {
    const grid = $(report.page.main).find(".dt-scrollable, .datatable");
    if (!grid.length) return;

    grid.off("click.fp_edit");
    grid.on("click.fp_edit", "td", function (e) {
        const $td = $(this);
        const col_idx = $td.index();
        const datatable = report.datatable;
        if (!datatable) return;

        // Find which column was clicked
        const col = datatable.datamanager.columns[col_idx];
        if (!col || col.fieldname !== "final_price") return;

        const row_idx = $td.closest("tr").attr("data-row-index");
        if (row_idx == null) return;

        const row = datatable.datamanager.data[parseInt(row_idx)];
        if (!row || !row.mreq_item_name) return;
        if (row.status === "Quoted") {
            frappe.show_alert({
                message: __("Cannot edit price on already-quoted line."),
                indicator: "orange",
            });
            return;
        }

        e.stopPropagation();
        prompt_final_price_edit(row, report);
    });
}


function prompt_final_price_edit(row, report) {
    frappe.prompt(
        [
            {
                fieldname: "final_price",
                label: __("Final Price (TZS)"),
                fieldtype: "Currency",
                default: row.final_price,
                reqd: 1,
            },
        ],
        function (values) {
            frappe.call({
                method: "iaes_custom.iaes_custom.iaes_custom.report.nmb_hq_monthly_billing.nmb_hq_monthly_billing.update_final_price",
                args: {
                    mreq_item_name: row.mreq_item_name,
                    final_price: values.final_price,
                },
                callback: function (r) {
                    if (r.message && r.message.ok) {
                        frappe.show_alert({
                            message: __("Final Price updated. Refreshing report…"),
                            indicator: "green",
                        });
                        report.refresh();
                    }
                },
            });
        },
        __("Edit Final Price"),
        __("Save")
    );
}


// ---------------------------------------------------------------------------
// Generate Quotation button handler
// ---------------------------------------------------------------------------
function generate_quotation(report) {
    const filters = report.get_values();
    if (!filters.project) {
        frappe.msgprint(__("Project filter is required."));
        return;
    }

    const data = report.data || [];
    const ready = data.filter(r => r.status === "Ready to quote");

    if (ready.length === 0) {
        frappe.msgprint({
            title: __("Nothing to quote"),
            message: __(
                "No lines have status 'Ready to quote' in the current view. " +
                "Lines need to have a cost source AND a Delivery Note AND not already be on a Quotation."
            ),
            indicator: "orange",
        });
        return;
    }

    // Show preview totals
    const total = ready.reduce(
        (sum, r) => sum + (r.final_price || 0) * (r.qty_ordered || 0),
        0
    );

    frappe.confirm(
        __(
            "Create Quotation for {0} lines totalling TZS {1}?<br><br>" +
            "Quotation will be created as Draft. Review and submit manually before sending to NMB.",
            [
                ready.length,
                format_currency(total, "TZS"),
            ]
        ),
        function () {
            frappe.call({
                method: "iaes_custom.iaes_custom.iaes_custom.report.nmb_hq_monthly_billing.generate_quotation.generate",
                args: {
                    project: filters.project,
                    from_date: filters.from_date,
                    to_date: filters.to_date,
                    mreq_item_names: ready.map(r => r.mreq_item_name),
                },
                freeze: true,
                freeze_message: __("Creating Quotation…"),
                callback: function (r) {
                    if (r.message && r.message.quotation) {
                        frappe.show_alert({
                            message: __(
                                "Quotation {0} created with {1} lines. Opening…",
                                [r.message.quotation, r.message.lines_count]
                            ),
                            indicator: "green",
                        });
                        setTimeout(() => {
                            frappe.set_route("Form", "Quotation", r.message.quotation);
                        }, 800);
                    } else {
                        frappe.msgprint(__("Quotation creation failed. See server logs."));
                    }
                },
            });
        }
    );
}
