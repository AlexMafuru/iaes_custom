frappe.query_reports["Visit Outcome Analysis"] = {
    filters: [
        {
            fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1,
        },
        {
            fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
            default: frappe.datetime.get_today(), reqd: 1,
        },
        {
            fieldname: "sales_person", label: __("Sales Person"),
            fieldtype: "Link", options: "Sales Person",
        },
        {
            fieldname: "territory", label: __("Territory"),
            fieldtype: "Link", options: "Territory",
        },

    ],
};
