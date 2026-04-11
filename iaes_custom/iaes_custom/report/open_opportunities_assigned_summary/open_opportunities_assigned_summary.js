frappe.query_reports["Open Opportunities Assigned Summary"] = {
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        if (column.fieldname === "open_count" && cint(data.open_count) > 0) {
            const filters = [
                ["Opportunity", "status", "in", ["Open", "In preparation", "In Preparation"]],
                ["Opportunity", "_assign", "like", `%${data.assigned_user}%`]
            ];

            const encoded = encodeURIComponent(JSON.stringify(filters));

            return `<a href="/app/opportunity/view/list?filters=${encoded}" style="font-weight:bold;">${data.open_count}</a>`;
        }

        if (column.fieldname === "expired_count" && cint(data.expired_count) > 0) {
            const filters = [
                ["Opportunity", "status", "in", ["Open", "In preparation", "In Preparation"]],
                ["Opportunity", "_assign", "like", `%${data.assigned_user}%`],
                ["Opportunity", "expected_closing", "<", frappe.datetime.get_today()]
            ];

            const encoded = encodeURIComponent(JSON.stringify(filters));

            return `<a href="/app/opportunity/view/list?filters=${encoded}" style="font-weight:bold;">${data.expired_count}</a>`;
        }

        return value;
    }
};