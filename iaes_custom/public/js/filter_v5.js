frappe.after_ajax(function () {
    if (!frappe.ui || !frappe.ui.Filter) return;
    if (frappe.ui.Filter.prototype._iaestz_v5) return;
    frappe.ui.Filter.prototype._iaestz_v5 = true;

    const original = frappe.ui.Filter.prototype.set_conditions;
    frappe.ui.Filter.prototype.set_conditions = function () {
        original.call(this);
        const ops = [">", "<", ">=", "<="];
        const fields_to_patch = [
            "Link", "Dynamic Link", "Data",
            "Small Text", "Select", "Text"
        ];
        fields_to_patch.forEach(ft => {
            if (this.invalid_condition_map && this.invalid_condition_map[ft]) {
                this.invalid_condition_map[ft] = this.invalid_condition_map[ft]
                    .filter(op => !ops.includes(op));
            }
        });
    };
});
