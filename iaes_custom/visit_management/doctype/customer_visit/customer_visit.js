// Copyright (c) 2026, Sales Team Strategy and contributors

frappe.ui.form.on("Customer Visit", {
    setup(frm) {
        frm.set_query("contact_person", function () {
            return {
                query: "frappe.contacts.doctype.contact.contact.contact_query",
                filters: {
                    link_doctype: frm.doc.party_type,
                    link_name: frm.doc.party || "",
                },
            };
        });

        frm.set_query("assigned_to", function () {
            return { filters: { enabled: 1, is_group: 0 } };
        });

        frm.set_query("reference_name", "visit_references", function (doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            const filters = {};
            if (doc.party_type === "Customer" &&
                ["Quotation", "Opportunity", "Project"].includes(row.reference_type)) {
                if (row.reference_type === "Project") {
                    filters.customer = doc.party;
                } else {
                    filters.party_name = doc.party;
                }
            }
            return { filters: filters };
        });
    },

    refresh(frm) {
        frm.trigger("render_status_banner");
        frm.trigger("add_action_buttons");
    },

    party_type(frm) {
        frm.set_value("party", null);
        frm.set_value("contact_person", null);
    },

    party(frm) {
        frm.set_value("contact_person", null);
        if (frm.doc.party) {
            frappe.call({
                method: "iaes_custom.visit_management.doctype.customer_visit.customer_visit.get_open_visit_count",
                args: { party_type: frm.doc.party_type, party: frm.doc.party },
                callback(r) {
                    if (r.message > 0 && frm.is_new()) {
                        frm.dashboard.add_comment(
                            __("This party already has {0} open visit(s).", [r.message]),
                            "orange", true
                        );
                    }
                },
            });
        }
    },

    render_status_banner(frm) {
        frm.dashboard.clear_headline();
        if (frm.is_new()) return;

        if (frm.doc.status === "Open" &&
            frm.doc.visit_date < frappe.datetime.get_today()) {
            frm.dashboard.set_headline(
                __("This visit is overdue. It was planned for {0}.", [
                    frappe.datetime.str_to_user(frm.doc.visit_date),
                ]),
                "red"
            );
        } else if (frm.doc.status === "Closed") {
            frm.dashboard.set_headline(
                __("Closed on {0} by {1}.", [
                    frappe.datetime.str_to_user(frm.doc.closed_on),
                    frm.doc.closed_by,
                ]),
                "green"
            );
        }

        if (frm.doc.reschedule_count > 0) {
            frm.dashboard.add_comment(
                __("Rescheduled {0} time(s). Originally planned for {1}.", [
                    frm.doc.reschedule_count,
                    frappe.datetime.str_to_user(frm.doc.original_planned_date),
                ]),
                "blue", true
            );
        }
    },

    add_action_buttons(frm) {
        if (frm.is_new()) return;

        if (["Open", "In Progress"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Close Visit"), () => open_close_dialog(frm))
                .addClass("btn-primary");
        }

        if (frm.doc.status === "Open") {
            frm.add_custom_button(__("Mark In Progress"), () => {
                frm.set_value("status", "In Progress");
                frm.save();
            });
        }

        if (["Open", "In Progress"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Cancel Visit"), () => {
                frappe.confirm(__("Cancel this visit?"), () => {
                    frm.set_value("status", "Cancelled");
                    frm.save();
                });
            });
        }

        if (frm.doc.status === "Closed") {
            frm.add_custom_button(__("New Visit"), () => {
                frappe.new_doc("Customer Visit", {
                    party_type: frm.doc.party_type,
                    party: frm.doc.party,
                    contact_person: frm.doc.contact_person,
                    assigned_to: frm.doc.assigned_to,
                });
            }, __("Create"));

            // OPTY first - matches the sales channel:
            // CV -> OPTY -> QTN -> SO/PROJ -> SINV -> PE
            frm.add_custom_button(__("Opportunity"), () => {
                frappe.new_doc("Opportunity", {
                    opportunity_from: frm.doc.party_type,
                    party_name: frm.doc.party,
                });
            }, __("Create"));

            if (frm.doc.party_type === "Customer") {
                frm.add_custom_button(__("Quotation"), () => {
                    frappe.new_doc("Quotation", {
                        quotation_to: "Customer",
                        party_name: frm.doc.party,
                    });
                }, __("Create"));
            }
        }

        if (frm.doc.follow_up_reference) {
            frm.add_custom_button(__("Follow-up Document"), () => {
                frappe.set_route("Form", frm.doc.follow_up_reference_type,
                    frm.doc.follow_up_reference);
            }, __("View"));
        }
    },
});

frappe.ui.form.on("Visit Reference", {
    reference_type(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "reference_name", null);
    },
});

function open_close_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Close Visit"),
        size: "large",
        fields: [
            {
                fieldname: "actual_visit_date", fieldtype: "Date",
                label: __("Actual Visit Date"), reqd: 1,
                default: frappe.datetime.get_today(),
            },
            {
                fieldname: "visit_outcome", fieldtype: "Select",
                label: __("Visit Outcome"), reqd: 1,
                options: frm.get_field("visit_outcome").df.options,
            },
            { fieldtype: "Column Break" },
            {
                fieldname: "next_step", fieldtype: "Select",
                label: __("Next Step"), reqd: 1,
                options: frm.get_field("next_step").df.options,
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "closing_remarks", fieldtype: "Text Editor",
                label: __("Closing Remarks"), reqd: 1,
                description: __("What was discussed and agreed."),
            },
            { fieldtype: "Section Break" },
            {
                fieldname: "follow_up_required", fieldtype: "Check",
                label: __("Follow-up Required"),
            },
            {
                fieldname: "follow_up_type", fieldtype: "Select",
                label: __("Follow-up Type"),
                depends_on: "follow_up_required",
                mandatory_depends_on: "eval:doc.follow_up_required==1",
                options: frm.get_field("follow_up_type").df.options,
            },
            { fieldtype: "Column Break" },
            {
                fieldname: "follow_up_date", fieldtype: "Date",
                label: __("Follow-up Date"),
                depends_on: "follow_up_required",
                mandatory_depends_on: "eval:doc.follow_up_required==1",
            },
        ],
        primary_action_label: __("Close Visit"),
        primary_action(values) {
            frappe.call({
                method: "iaes_custom.visit_management.doctype.customer_visit.customer_visit.close_visit",
                args: Object.assign({ name: frm.doc.name }, values),
                freeze: true,
                freeze_message: __("Closing visit..."),
                callback() {
                    d.hide();
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Visit closed"), indicator: "green",
                    });
                },
            });
        },
    });
    d.show();
}
