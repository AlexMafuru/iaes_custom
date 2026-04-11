frappe.query_reports["Open Opportunities Assigned Summary"] = {
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        if (column.fieldname === "open_count" && cint(data.open_count) > 0) {
            return `<a href="#" class="oaas-link" data-kind="open" data-user="${frappe.utils.escape_html(data.assigned_user)}">${data.open_count}</a>`;
        }

        if (column.fieldname === "expired_count" && cint(data.expired_count) > 0) {
            return `<a href="#" class="oaas-link" data-kind="expired" data-user="${frappe.utils.escape_html(data.assigned_user)}">${data.expired_count}</a>`;
        }

        return value;
    },

    after_datatable_render: function () {
        const wrapper = $('.query-report');

        wrapper.off('click', '.oaas-link');

        wrapper.on('click', '.oaas-link', function (e) {
            e.preventDefault();
            e.stopPropagation();

            const user = $(this).attr('data-user');
            const kind = $(this).attr('data-kind');

            const filters = [
                ["Opportunity", "status", "in", ["Open", "In preparation", "In Preparation"]],
                ["Opportunity", "_assign", "like", `%${user}%`]
            ];

            if (kind === "expired") {
                filters.push(["Opportunity", "expected_closing", "<", frappe.datetime.get_today()]);
            }

            frappe.set_route("List", "Opportunity", filters);
        });
    }
};
