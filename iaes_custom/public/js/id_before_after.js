frappe.ready(function () {
    if (!frappe.ui || !frappe.ui.Filter) return;

    const Filter = frappe.ui.Filter;

    if (Filter.prototype._before_after_patched) return;
    Filter.prototype._before_after_patched = true;

    const original_get_operators = Filter.prototype.get_operators;
    const original_make = Filter.prototype.make;
    const original_set_field = Filter.prototype.set_field;

    function is_name_field(filter) {
        try {
            return (
                filter?.fieldname === "name" ||
                filter?.df?.fieldname === "name" ||
                filter?.field?.df?.fieldname === "name"
            );
        } catch (e) {
            return false;
        }
    }

    function relabel_operators(filter) {
        if (!is_name_field(filter)) return;

        const $select =
            filter?.operator_input?.$input ||
            filter?.condition?.$input ||
            null;

        if (!$select || !$select.length) return;

        $select.find('option[value="<"]').text("Before");
        $select.find('option[value=">"]').text("After");
    }

    Filter.prototype.get_operators = function (df) {
        let operators = original_get_operators
            ? original_get_operators.call(this, df)
            : [];

        if (df && df.fieldname === "name") {
            if (!operators.includes("<")) operators.push("<");
            if (!operators.includes(">")) operators.push(">");
        }

        return operators;
    };

    Filter.prototype.make = function () {
        const result = original_make ? original_make.apply(this, arguments) : undefined;
        setTimeout(() => relabel_operators(this), 100);
        return result;
    };

    Filter.prototype.set_field = function () {
        const result = original_set_field
            ? original_set_field.apply(this, arguments)
            : undefined;
        setTimeout(() => relabel_operators(this), 100);
        return result;
    };
});
