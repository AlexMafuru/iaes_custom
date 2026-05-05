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

        return value;
    },

    onload: function (report) {
        // "Generate Quotation" button — pulls selected rows into a draft QTN
        report.page.add_inner_button(__("Generate Quotation"), function () {
            generate_quotation(report);
        }).addClass("btn-primary");
    },
};


// ---------------------------------------------------------------------------
// (Inline edit on Final Price was removed in favour of computing prices on
// the fly each report run. To override a price, edit the rate on the
// generated Quotation before submitting — the QTN is the single source of
// truth for the customer-facing rate.)
// ---------------------------------------------------------------------------


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
                    lines_payload: ready.map(r => ({
                        mreq_item_name: r.mreq_item_name,
                        final_price: r.final_price,
                        pricing_comment: r.pricing_comment || "",
                    })),
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
