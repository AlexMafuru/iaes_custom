frappe.query_reports["Customer Performance 3-Year Funnel"] = {
    filters: [
        {
            fieldname: "from_year",
            label: "From Year",
            fieldtype: "Int",
            default: new Date().getFullYear() - 2,
            reqd: 1
        },
        {
            fieldname: "to_year",
            label: "To Year",
            fieldtype: "Int",
            default: new Date().getFullYear(),
            reqd: 1
        },
        {
            fieldname: "customer",
            label: "Customer",
            fieldtype: "Link",
            options: "Customer"
        },
        {
            fieldname: "customer_group",
            label: "Customer Group",
            fieldtype: "Link",
            options: "Customer Group"
        },
        {
            fieldname: "territory",
            label: "Territory",
            fieldtype: "Link",
            options: "Territory"
        }
    ],

    onload: function(report) {
        report.page.add_inner_button("This Year Only", function() {
            const y = new Date().getFullYear();
            report.set_filter_value("from_year", y);
            report.set_filter_value("to_year", y);
            report.refresh();
        });

        report.page.add_inner_button("Last 3 Years", function() {
            const y = new Date().getFullYear();
            report.set_filter_value("from_year", y - 2);
            report.set_filter_value("to_year", y);
            report.refresh();
        });
    }
};