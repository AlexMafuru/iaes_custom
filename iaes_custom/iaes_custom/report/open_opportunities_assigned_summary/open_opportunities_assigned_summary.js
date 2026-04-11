frappe.query_reports["Open Opportunities Assigned Summary"] = {
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        // OPEN opportunities link
        if (column.fieldname === "open_count" && cint(data.open_count) > 0) {
            return `<a href="#" 
                style="color:red;font-weight:bold;" 
                onclick="frappe.query_reports['Open Opportunities Assigned Summary'].open_opportunities('${data.assigned_user}'); return false;">
                TEST-${data.open_count}
            </a>`;
        }

        // EXPIRED opportunities link
        if (column.fieldname === "expired_count" && cint(data.expired_count) > 0) {
            return `<a href="#" 
                style="color:green;font-weight:bold;" 
                onclick="frappe.query_reports['Open Opportunities Assigned Summary'].open_expired_opportunities('${data.assigned_user}'); return false;">
                EXP-${data.expired_count}
            </a>`;
        }

        return value;
    },

    // OPEN opportunities drill-down
    open_opportunities: function (assigned_user) {

        const filters = [
            ["Opportunity", "status", "in", ["Open", "In preparation", "In Preparation"]],
            ["Opportunity", "_assign", "like", `%${assigned_user}%`]
        ];

        const encoded = encodeURIComponent(JSON.stringify(filters));

        window.location.href =
            `/app/opportunity/view/list?filters=${encoded}`;
    },

    // EXPIRED opportunities drill-down
    open_expired_opportunities: function (assigned_user) {

        const filters = [
            ["Opportunity", "status", "in", ["Open", "In preparation", "In Preparation"]],
            ["Opportunity", "_assign", "like", `%${assigned_user}%`],
            ["Opportunity", "expected_closing", "<", frappe.datetime.get_today()]
        ];

        const encoded = encodeURIComponent(JSON.stringify(filters));

        window.location.href =
            `/app/opportunity/view/list?filters=${encoded}`;
    }
};