frappe.after_ajax(function () {

    function patch_filter_options(proto) {
        if (!proto || proto._iaestz_patched) return;
        proto._iaestz_patched = true;

        const original = proto.get_filter_options;
        if (!original) return;

        proto.get_filter_options = function (fieldtype) {
            let result = original.call(this, fieldtype);

            const target_types = [
                "Data", "Small Text", "Text",
                "Long Text", "Link", "Dynamic Link"
            ];

            if (target_types.includes(fieldtype)) {
                const extras = [">=", "<=", ">", "<"];
                extras.forEach(op => {
                    if (!result.includes(op)) {
                        const idx = result.indexOf("!=");
                        if (idx !== -1) {
                            result.splice(idx + 1, 0, op);
                        } else {
                            result.push(op);
                        }
                    }
                });
            }
            return result;
        };
    }

    if (frappe.ui) {
        if (frappe.ui.FilterList) patch_filter_options(frappe.ui.FilterList.prototype);
        if (frappe.ui.Filter) patch_filter_options(frappe.ui.Filter.prototype);
    }
});