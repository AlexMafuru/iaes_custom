// Site Delivery Note — client-side controller
// Path: iaes_custom/iaes_custom/doctype/site_delivery_note/site_delivery_note.js

frappe.ui.form.on("Site Delivery Note", {

    refresh: function (frm) {

        // ── Action buttons (only when submitted) ────────────────────────────
        if (frm.doc.docstatus === 1) {

            // Create Purchase Receipt (for PO/PINV-sourced lines)
            const has_prec_eligible = (frm.doc.items || []).some(
                r => (r.source_doctype === "Purchase Order" ||
                      r.source_doctype === "Purchase Invoice")
                     && !r.prec_created
            );

            if (has_prec_eligible) {
                frm.add_custom_button(__("Create Purchase Receipt"), function () {
                    create_prec_dialog(frm);
                }, __("Create"));
            }

            // Show downstream status (PREC / Quoted / Invoiced bars)
            refresh_status_html(frm);
        }

        // ── Get Items From dialog (only when editable) ──────────────────────
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Get Items From"), function () {
                open_get_items_dialog(frm);
            });
        }
    },

    project: function (frm) {
        // Clear items if project changes — pulled lines were project-specific
        if (frm.doc.docstatus === 0 && (frm.doc.items || []).length > 0) {
            frappe.confirm(
                __("Project changed. Clear existing item lines? They may not match the new project."),
                function () {
                    frm.clear_table("items");
                    frm.refresh_field("items");
                }
            );
        }
    },
});


// ════════════════════════════════════════════════════════════════════════════
//  GET ITEMS FROM DIALOG
// ════════════════════════════════════════════════════════════════════════════

function open_get_items_dialog (frm) {
    if (!frm.doc.project) {
        frappe.msgprint(__("Set Project first."));
        return;
    }

    const d = new frappe.ui.Dialog({
        title: __("Get Items From Source Document"),
        size: "extra-large",
        fields: [
            {
                fieldname: "source_doctype",
                label: __("Source Type"),
                fieldtype: "Select",
                options: ["Purchase Invoice", "Purchase Order",
                          "Stock Entry", "Expense Claim"].join("\n"),
                default: "Purchase Invoice",
                reqd: 1,
            },
            {
                fieldname: "col1",
                fieldtype: "Column Break",
            },
            {
                fieldname: "from_date",
                label: __("From Date"),
                fieldtype: "Date",
                default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            },
            {
                fieldname: "to_date",
                label: __("To Date"),
                fieldtype: "Date",
                default: frappe.datetime.get_today(),
            },
            {
                fieldname: "fetch_btn",
                fieldtype: "Button",
                label: __("Fetch Eligible Lines"),
                click: function () {
                    fetch_eligible_lines(d, frm);
                },
            },
            {
                fieldname: "results_section",
                fieldtype: "Section Break",
                label: __("Eligible Lines"),
            },
            {
                fieldname: "results_html",
                fieldtype: "HTML",
            },
        ],
        primary_action_label: __("Add Selected to SDN"),
        primary_action: function () {
            const selected = collect_selected_lines(d);
            if (!selected.length) {
                frappe.msgprint(__("No lines selected."));
                return;
            }
            selected.forEach(row => {
                const child = frm.add_child("items");
                Object.assign(child, row);
                child.amount = (parseFloat(row.qty) || 0)
                              * (parseFloat(row.unit_cost) || 0);
            });
            frm.refresh_field("items");
            d.hide();
        },
    });

    d.show();
}


function fetch_eligible_lines (dialog, frm) {
    const source_doctype = dialog.get_value("source_doctype");
    const from_date = dialog.get_value("from_date");
    const to_date = dialog.get_value("to_date");

    if (!source_doctype) {
        frappe.msgprint(__("Pick a source type first."));
        return;
    }

    frappe.call({
        method: "iaes_custom.iaes_custom.doctype.site_delivery_note."
              + "site_delivery_note.get_pullable_lines",
        args: {
            project: frm.doc.project,
            source_doctype: source_doctype,
            from_date: from_date,
            to_date: to_date,
        },
        freeze: true,
        freeze_message: __("Searching eligible lines…"),
        callback: function (r) {
            render_eligible_lines(dialog, r.message || []);
        },
    });
}


function render_eligible_lines (dialog, lines) {
    const wrapper = dialog.fields_dict.results_html.$wrapper;
    wrapper.empty();

    if (!lines.length) {
        wrapper.html(`<div style="padding:20px;text-align:center;color:#999;">
            ${__("No eligible lines found. Either nothing matches the filters, "
              + "or all matching lines have already been pulled into other SDNs.")}
        </div>`);
        return;
    }

    let html = `
        <div style="max-height:400px;overflow-y:auto;border:1px solid #ddd;">
        <table class="table table-sm" style="margin:0;font-size:12px;">
        <thead style="position:sticky;top:0;background:#f8f9fa;z-index:1;">
            <tr>
                <th style="width:30px;"><input type="checkbox" id="sdn-select-all"></th>
                <th>${__("Date")}</th>
                <th>${__("Source")}</th>
                <th>${__("Item")}</th>
                <th>${__("Description")}</th>
                <th class="text-right">${__("Qty")}</th>
                <th>${__("UoM")}</th>
                <th class="text-right">${__("Unit Cost")}</th>
                <th class="text-right">${__("Amount")}</th>
                <th>${__("Supplier")}</th>
            </tr>
        </thead>
        <tbody>
    `;

    lines.forEach((line, idx) => {
        const route_doctype = line.source_doctype.toLowerCase().replace(/ /g, "-");
        html += `
            <tr data-idx="${idx}">
                <td><input type="checkbox" class="sdn-line-check" data-idx="${idx}"></td>
                <td>${line.posting_date || ""}</td>
                <td><a href="/app/${route_doctype}/${line.source_document}"
                       target="_blank" style="font-size:11px;">${line.source_document}</a></td>
                <td>${line.item_code || ""}</td>
                <td style="max-width:250px;">${line.item_name || line.description || ""}</td>
                <td class="text-right">${parseFloat(line.qty || 0).toFixed(2)}</td>
                <td>${line.uom || ""}</td>
                <td class="text-right">${format_currency(line.unit_cost)}</td>
                <td class="text-right">${format_currency(line.amount)}</td>
                <td>${line.supplier || ""}</td>
            </tr>
        `;
    });

    html += "</tbody></table></div>";
    wrapper.html(html);

    // Stash the lines on the dialog for retrieval at OK time
    dialog._eligible_lines = lines;

    // Select-all toggle
    wrapper.find("#sdn-select-all").on("change", function () {
        const checked = $(this).prop("checked");
        wrapper.find(".sdn-line-check").prop("checked", checked);
    });
}


function collect_selected_lines (dialog) {
    const wrapper = dialog.fields_dict.results_html.$wrapper;
    const eligible = dialog._eligible_lines || [];
    const selected = [];

    wrapper.find(".sdn-line-check:checked").each(function () {
        const idx = parseInt($(this).data("idx"), 10);
        const line = eligible[idx];
        if (line) selected.push(line);
    });

    return selected;
}


function format_currency (v) {
    if (v === null || v === undefined || v === "") return "";
    const num = parseFloat(v);
    if (isNaN(num)) return "";
    return num.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}


// ════════════════════════════════════════════════════════════════════════════
//  CREATE PURCHASE RECEIPT DIALOG
// ════════════════════════════════════════════════════════════════════════════

function create_prec_dialog (frm) {
    const d = new frappe.ui.Dialog({
        title: __("Create Purchase Receipt"),
        fields: [
            {
                fieldname: "target_warehouse",
                label: __("Target Warehouse (Delivery Warehouse)"),
                fieldtype: "Link",
                options: "Warehouse",
                reqd: 1,
                description: __(
                    "PREC will receive stock into this warehouse. Typically "
                    + "the 'NMB HQ Delivery Warehouse' or similar."
                ),
            },
            {
                fieldname: "info",
                fieldtype: "HTML",
                options: `<div class="text-muted" style="margin-top:10px;">
                    ${__("Only lines from Purchase Order or Purchase Invoice "
                       + "will be included. Stock Entry / Expense Claim lines "
                       + "are skipped (their stock recognition belongs to "
                       + "those source doctypes).")}
                </div>`,
            },
        ],
        primary_action_label: __("Create"),
        primary_action: function (values) {
            frappe.call({
                method: "iaes_custom.iaes_custom.doctype.site_delivery_note."
                      + "site_delivery_note.make_purchase_receipt_from_sdn",
                args: {
                    sdn_name: frm.doc.name,
                    target_warehouse: values.target_warehouse,
                },
                freeze: true,
                freeze_message: __("Creating Purchase Receipt(s)…"),
                callback: function (r) {
                    if (r.message && r.message.length) {
                        const links = r.message.map(
                            n => `<a href='/app/purchase-receipt/${n}'>${n}</a>`
                        ).join(", ");
                        frappe.show_alert({
                            message: __("Created: {0}", [links]),
                            indicator: "green",
                        }, 10);
                        frm.reload_doc();
                    }
                    d.hide();
                },
            });
        },
    });

    d.show();
}


// ════════════════════════════════════════════════════════════════════════════
//  STATUS REFRESH
// ════════════════════════════════════════════════════════════════════════════

function refresh_status_html (frm) {
    frappe.call({
        method: "iaes_custom.iaes_custom.doctype.site_delivery_note."
              + "site_delivery_note.get_downstream_status_html",
        args: { sdn_name: frm.doc.name },
        callback: function (r) {
            if (r.message) {
                frm.get_field("prec_status_html").$wrapper.html(r.message.prec_html);
                frm.get_field("quotation_status_html").$wrapper.html(r.message.qtn_html);
            }
        },
    });
}
