frappe.query_reports["Open Opportunities Assigned Summary"] = {
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        if (column.fieldname === "open_count" && cint(data.open_count) > 0) {
            return `<a href="${data.open_url}" style="font-weight:bold;">${data.open_count}</a>`;
        }

        if (column.fieldname === "expired_count" && cint(data.expired_count) > 0) {
            return `<a href="${data.expired_url}" style="font-weight:bold;">${data.expired_count}</a>`;
        }

        if (column.fieldname === "closing_week" && cint(data.closing_week) > 0) {
            return `<a href="${data.closing_week_url}" style="font-weight:bold;">${data.closing_week}</a>`;
        }

        return value;
    }
};