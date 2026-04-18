// Remote Site Biometric Attendance Analysis (v3)
// =================================================
// ERPNext Script Report — JavaScript file

frappe.query_reports["Remote Site Attendance Analysis"] = {

    filters: [
        {fieldname:"from_date",label:__("From Date"),fieldtype:"Date",default:frappe.datetime.month_start(),reqd:1},
        {fieldname:"to_date",label:__("To Date"),fieldtype:"Date",default:frappe.datetime.month_end(),reqd:1},
        {fieldname:"employee",label:__("Employee"),fieldtype:"Link",options:"Employee",get_query:()=>({filters:{status:"Active"}})},
        {fieldname:"department",label:__("Department"),fieldtype:"Link",options:"Department"},
        {fieldname:"site",label:__("Site / Branch"),fieldtype:"Data",default:"NMB"},
        {fieldname:"report_mode",label:__("Report Mode"),fieldtype:"Select",options:"Summary\nDaily Detail",default:"Summary",reqd:1},
    ],

    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        const mode = frappe.query_report.get_filter_value("report_mode");

        const drilldown = (emp_id, emp_name, label, count) => {
            if (!count || parseFloat(count) === 0) return `<span>${count}</span>`;
            return `<a href="#" title="Click to see ${label} days for ${emp_name}"
                onclick="frappe.query_report.set_filter_value('employee','${emp_id}');frappe.query_report.set_filter_value('report_mode','Daily Detail');frappe.query_report.refresh();return false;"
                style="text-decoration:underline;cursor:pointer;font-weight:600;">${count}</a>`;
        };

        const openCheckin = (emp_id, emp_name, count) => {
            if (!count || parseFloat(count) === 0) return `<span>${count}</span>`;
            return `<a href="#" title="View Employee Checkin for ${emp_name}"
                onclick="frappe.route_options={employee:'${emp_id}'};frappe.set_route('List','Employee Checkin');return false;"
                style="text-decoration:underline;cursor:pointer;font-weight:600;color:#e74c3c;">${count}</a>`;
        };

        if (column.fieldname === "employee_name" && mode === "Summary") {
            return `<a href="#" onclick="frappe.query_report.set_filter_value('employee','${data.employee}');frappe.query_report.set_filter_value('report_mode','Daily Detail');frappe.query_report.refresh();return false;"
                style="font-weight:600;text-decoration:underline;cursor:pointer;color:var(--text-color);">${data.employee_name}</a>`;
        }

        if (column.fieldname === "present_days")
            return drilldown(data.employee, data.employee_name, "present", data.present_days);

        if (column.fieldname === "absent_days") {
            const v = parseFloat(data.absent_days) || 0;
            const h = drilldown(data.employee, data.employee_name, "absent", data.absent_days);
            return v >= 3 ? h.replace("font-weight:600", "font-weight:600;color:#e74c3c") : h;
        }

        if (column.fieldname === "late_entries") {
            const v = parseInt(data.late_entries) || 0;
            const h = drilldown(data.employee, data.employee_name, "late", data.late_entries);
            return v >= 3 ? h.replace("font-weight:600", "font-weight:600;color:#e67e22") : h;
        }

        if (column.fieldname === "early_exits")
            return drilldown(data.employee, data.employee_name, "early exit", data.early_exits);

        if (column.fieldname === "missing_punches")
            return openCheckin(data.employee, data.employee_name, data.missing_punches);

        if (column.fieldname === "overtime_hours") {
            const v = parseFloat(data.overtime_hours) || 0;
            if (v > 0) return `<span style="color:#2980b9;font-weight:600;">${v.toFixed(1)}</span>`;
        }

        if (column.fieldname === "attendance_pct") {
            const pct = parseFloat(data.attendance_pct) || 0;
            const col = pct >= 95 ? "#27ae60" : pct >= 85 ? "#2ecc71" : pct >= 75 ? "#f39c12" : "#e74c3c";
            return `<div style="display:flex;align-items:center;gap:6px;">
                <div style="flex:1;height:8px;background:#eee;border-radius:4px;overflow:hidden;min-width:55px;">
                <div style="width:${Math.min(pct,100)}%;height:100%;background:${col};border-radius:4px;"></div></div>
                <span style="min-width:38px;font-size:12px;">${pct.toFixed(1)}%</span></div>`;
        }

        if (column.fieldname === "status_summary") {
            const map = {"Excellent":"green","Good":"blue","Moderate":"orange","Needs Attention":"red"};
            return `<span class="indicator-pill ${map[data.status_summary]||'grey'}">${data.status_summary}</span>`;
        }

        if (column.fieldname === "attendance_date" && data.attendance_date) {
            return `<a href="#" title="View checkin for ${data.attendance_date}"
                onclick="frappe.route_options={employee:'${data.employee}'};frappe.set_route('List','Employee Checkin');return false;"
                style="text-decoration:underline;cursor:pointer;color:var(--text-color);">${data.attendance_date}</a>`;
        }

        if (column.fieldname === "first_in") {
            const isLate = data.late_entry && data.late_entry !== "On time" && data.late_entry !== "-";
            if (isLate) return `<span style="color:#e67e22;font-weight:600;">${data.first_in} (${data.late_entry})</span>`;
        }

        if (column.fieldname === "last_out") {
            const isEarly = data.early_exit && data.early_exit !== "Normal" && data.early_exit !== "-";
            if (isEarly) return `<span style="color:#e67e22;font-weight:600;">${data.last_out} (${data.early_exit})</span>`;
        }

        if (column.fieldname === "missing_punch" && data.missing_punch && data.missing_punch !== "-")
            return `<span style="color:#e74c3c;font-weight:600;">${data.missing_punch}</span>`;

        if (column.fieldname === "day_status") {
            const map = {"Present":"green","Overtime":"blue","Late":"orange","Early Exit":"orange","Late + Early":"red","Incomplete":"red","Absent":"red"};
            return `<span class="indicator-pill ${map[data.day_status]||'grey'}">${data.day_status}</span>`;
        }

        return value;
    },

    onload(report) {
        report.page.add_inner_button(__("Today"), () => {
            const t = frappe.datetime.get_today();
            frappe.query_report.set_filter_value("from_date", t);
            frappe.query_report.set_filter_value("to_date", t);
            frappe.query_report.refresh();
        });
        report.page.add_inner_button(__("This Week"), () => {
            frappe.query_report.set_filter_value("from_date", frappe.datetime.week_start());
            frappe.query_report.set_filter_value("to_date", frappe.datetime.week_end());
            frappe.query_report.refresh();
        });
        report.page.add_inner_button(__("This Month"), () => {
            frappe.query_report.set_filter_value("from_date", frappe.datetime.month_start());
            frappe.query_report.set_filter_value("to_date", frappe.datetime.month_end());
            frappe.query_report.refresh();
        });
        report.page.add_inner_button(__("Last Month"), () => {
            const last = frappe.datetime.add_months(frappe.datetime.month_start(), -1);
            frappe.query_report.set_filter_value("from_date", last);
            frappe.query_report.set_filter_value("to_date", frappe.datetime.month_end(last));
            frappe.query_report.refresh();
        });
        report.page.add_inner_button(__("Back to Summary"), () => {
            frappe.query_report.set_filter_value("employee", "");
            frappe.query_report.set_filter_value("report_mode", "Summary");
            frappe.query_report.refresh();
        });
    },
};
