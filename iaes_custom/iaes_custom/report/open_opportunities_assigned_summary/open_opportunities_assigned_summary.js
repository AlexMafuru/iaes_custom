frappe.query_reports["Open Opportunities Assigned Summary"] = {
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        if (column.fieldname === "open_count" && cint(data.open_count) > 0) {
            return `<a href="#" onclick="frappe.query_reports['Open Opportunities Assigned Summary'].open_opportunities('${data.assigned_user}'); return false;">${data.open_count}</a>`;
        }

        if (column.fieldname === "expired_count" && cint(data.expired_count) > 0) {
            return `<a href="#" onclick="frappe.query_reports['Open Opportunities Assigned Summary'].open_expired_opportunities('${data.assigned_user}'); return false;">${data.expired_count}</a>`;
        }

        return value;
    },

    open_opportunities: function (assigned_user) {
        frappe.set_route("List", "Opportunity", {
            _assign: ["like", `%${assigned_user}%`],
            status: "Open"
        });
    },

    open_expired_opportunities: function (assigned_user) {
        frappe.set_route("List", "Opportunity", {
            _assign: ["like", `%${assigned_user}%`],
            status: "Open",
            expected_closing: ["<", frappe.datetime.get_today()]
        });
    }
};