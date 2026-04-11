frappe.query_reports["Open Opportunities Assigned Summary"] = {
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        if (column.fieldname === "open_count" && cint(data.open_count) > 0) {
            return `<a href="#" onclick="alert('OPEN CLICK: ${data.assigned_user}'); return false;" style="font-weight:bold; color:#2563eb;">OPEN-${data.open_count}</a>`;
        }

        if (column.fieldname === "expired_count" && cint(data.expired_count) > 0) {
            return `<a href="#" onclick="alert('EXPIRED CLICK: ${data.assigned_user}'); return false;" style="font-weight:bold; color:#dc2626;">EXP-${data.expired_count}</a>`;
        }

        return value;
    }
};
