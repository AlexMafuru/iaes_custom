frappe.query_reports["Customer Performance 3-Year Funnel"] = {
    filters: [
        {
            fieldname: "from_year",
            label: __("From Year"),
            fieldtype: "Int",
            default: new Date().getFullYear() - 2,
            reqd: 1
        },
        {
            fieldname: "to_year",
            label: __("To Year"),
            fieldtype: "Int",
            default: new Date().getFullYear(),
            reqd: 1
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer"
        },
        {
            fieldname: "customer_group",
            label: __("Customer Group"),
            fieldtype: "Link",
            options: "Customer Group"
        },
        {
            fieldname: "territory",
            label: __("Territory"),
            fieldtype: "Link",
            options: "Territory"
        }
    ]
};