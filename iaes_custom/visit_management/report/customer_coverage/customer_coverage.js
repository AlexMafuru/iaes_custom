frappe.query_reports["Customer Coverage"] = {
    filters: [
        {
            fieldname: "territory", label: __("Territory"),
            fieldtype: "Link", options: "Territory",
        },
        {
            fieldname: "customer_group", label: __("Customer Group"),
            fieldtype: "Link", options: "Customer Group",
        },
        {
            fieldname: "only_neglected", label: __("Only Neglected / Never Visited"),
            fieldtype: "Check", default: 1,
        },
    ],

    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "coverage_status" && data) {
            const colors = {
                [__("Never Visited")]: "red",
                [__("Neglected")]: "orange",
                [__("Due Soon")]: "blue",
                [__("Covered")]: "green",
            };
            const c = colors[data.coverage_status];
            if (c) value = `<span class="indicator-pill ${c}">${data.coverage_status}</span>`;
        }
        if (column.fieldname === "days_since" && data && data.days_since === 9999) {
            value = "&#8212;";
        }
        return value;
    },
};
