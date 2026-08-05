frappe.query_reports["Visit Register"] = {
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
        {
            fieldname: "party_type", label: __("Party Type"),
            fieldtype: "Select", options: "\nCustomer\nLead",
        },
        {
            fieldname: "status", label: __("Status"), fieldtype: "Select",
            options: "\nOpen\nIn Progress\nClosed\nCancelled",
        },
        {
            fieldname: "visit_purpose", label: __("Visit Purpose"),
            fieldtype: "Select",
            options: "\nNew Business / Prospecting\nQuotation Follow-up\nProject Review / Site Meeting\nTechnical / Product Demonstration\nPayment Collection\nComplaint Resolution\nCourtesy / Relationship\nContract Renewal",
        },
        {
            fieldname: "only_overdue", label: __("Only Overdue"),
            fieldtype: "Check",
        },
    ],
};
