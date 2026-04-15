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
            // Enhancement 2: Company filter
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company")
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
    ],

    // Enhancement 5: conditional row colors based on indicator field
    get_datatable_options(options) {
        return Object.assign(options, {
            hooks: {
                columnTotal: frappe.utils.report_column_total
            }
        });
    },

    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        // Enhancement 5: color entire row based on performance indicator
        const indicator = data.indicator;

        if (data.customer === "TOTAL") {
            // Bold the total row
            value = `<strong>${value}</strong>`;
        } else if (column.fieldname === "customer") {
            // Show colored dot next to customer name
            const color = indicator === "Green" ? "#28a745"
                : indicator === "Red" ? "#dc3545"
                : indicator === "Orange" ? "#fd7e14"
                : "#17a2b8";
            value = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px;vertical-align:middle;"></span>${value}`;
        } else if (column.fieldname === "customer_type") {
            // Enhancement 4: badge for New vs Returning
            if (value === "New") {
                value = `<span style="background:#d4edda;color:#155724;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;">New</span>`;
            } else if (value === "Returning") {
                value = `<span style="background:#d1ecf1;color:#0c5460;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;">Returning</span>`;
            }
        }

        // Enhancement 7: color conversion % cells
        if (column.fieldname && column.fieldname.startsWith("conv_")) {
            const num = parseFloat(data[column.fieldname] || 0);
            if (num >= 50) {
                value = `<span style="color:#28a745;font-weight:500;">${value}</span>`;
            } else if (num > 0 && num < 50) {
                value = `<span style="color:#fd7e14;">${value}</span>`;
            } else if (num === 0 && data.customer !== "TOTAL") {
                value = `<span style="color:#dc3545;">${value}</span>`;
            }
        }

        return value;
    }
};