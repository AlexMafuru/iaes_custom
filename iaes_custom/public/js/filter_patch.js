frappe.after_ajax(function () {
    if (!frappe.ui || !frappe.ui.Filter) return;
    if (frappe.ui.Filter.prototype._iaestz_v3) return;
    frappe.ui.Filter.prototype._iaestz_v3 = true;

    const original_set_conditions = frappe.ui.Filter.prototype.set_conditions;

    frappe.ui.Filter.prototype.set_conditions = function () {
        original_set_conditions.call(this);

        const target_types = [
            "Data", "Small Text", "Text",
            "Long Text", "Link", "Dynamic Link"
        ];

        if (target_types.includes(this.fieldtype)) {
            const extras = [">", "<", ">=", "<="];
            const $select = this.field && this.field.$select;
            if (!$select) return;

            extras.forEach(op => {
                if (!$select.find(`option[value="${op}"]`).length) {
                    const $notEq = $select.find('option[value="!="]');
                    const $opt = $(`<option value="${op}">${op}</option>`);
                    if ($notEq.length) {
                        $notEq.after($opt);
                    } else {
                        $select.append($opt);
                    }
                }
            });
            $select.trigger("change");
        }
    };
});