frappe.after_ajax(function () {
    if (!frappe.ui || !frappe.ui.Filter) return;
    if (frappe.ui.Filter.prototype._iaestz_v2) return;
    frappe.ui.Filter.prototype._iaestz_v2 = true;

    const original_make_select = frappe.ui.Filter.prototype.make_select;

    frappe.ui.Filter.prototype.make_select = function () {
        original_make_select.call(this);

        const target_types = [
            "Data", "Small Text", "Text",
            "Long Text", "Link", "Dynamic Link"
        ];

        if (target_types.includes(this.fieldtype)) {
            const extras = [">=", "<=", ">", "<"];
            const select = this.field && this.field.$select;
            if (!select) return;

            extras.forEach(op => {
                const exists = select.find(`option[value="${op}"]`).length;
                if (!exists) {
                    const notEquals = select.find('option[value="!="]');
                    if (notEquals.length) {
                        notEquals.after(`<option value="${op}">${op}</option>`);
                    } else {
                        select.append(`<option value="${op}">${op}</option>`);
                    }
                }
            });
        }
    };
});
// v2 - make_select patch
