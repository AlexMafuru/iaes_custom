frappe.after_ajax(function () {
    if (!frappe.ui || !frappe.ui.Filter) return;
    if (frappe.ui.Filter.prototype._iaestz_v4) return;
    frappe.ui.Filter.prototype._iaestz_v4 = true;

    const original_set_conditions = frappe.ui.Filter.prototype.set_conditions;

    frappe.ui.Filter.prototype.set_conditions = function () {
        original_set_conditions.call(this);

        // Remove >, <, >=, <= from invalid conditions for Link and Data fields
        const ops_to_allow = [">", "<", ">=", "<="];
        const fields_to_patch = ["Link", "Dynamic Link", "Data", "Small Text"];

        fields_to_patch.forEach(fieldtype => {
            if (this.invalid_condition_map[fieldtype]) {
                this.invalid_condition_map[fieldtype] = this.invalid_condition_map[fieldtype]
                    .filter(op => !ops_to_allow.includes(op));
            }
        });
    };
});