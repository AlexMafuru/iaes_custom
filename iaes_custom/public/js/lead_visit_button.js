frappe.ui.form.on("Lead", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Visit"), () => {
            frappe.new_doc("Customer Visit", {
                party_type: "Lead",
                party: frm.doc.name,
            });
        }, __("Create"));
    },
});
