// Remote Site Biometric Attendance Analysis  (v2)
// =================================================
// ERPNext Script Report — JavaScript file
// Paste into the Script (JS) section when creating the report in UI.

frappe.query_reports["Remote Site Attendance Analysis"] = {

    // ─── FILTERS ────────────────────────────────────────────────────────────
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            reqd: 1,
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
            get_query: () => ({ filters: { status: "Active" } }),
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "site",
            label: __("Site / Branch"),
            fieldtype: "Data",
            default: "NMB",
        },
        {
            fieldname: "report_mode",
            label: __("Report Mode"),
            fieldtype: "Select",
            options: "Summary\nDaily Detail",
            default: "Summary",
            reqd: 1,
        },
    ],

    // ─── FORMATTER ──────────────────────────────────────────────────────────
    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // ── Status summary pill (Summary mode) ──────────────────────────
        if (column.fieldname === "status_summary") {
            const map = {
                "Excellent":       "green",
                "Good":            "blue",
                "Moderate":        "orange",
                "Needs Attention": "red",
            };
            const c = map[data.status_summary] || "grey";
            return `<span class="indicator-pill ${c}">${data.status_summary}</span>`;
        }

        // ── Attendance % progress bar ────────────────────────────────────
        if (column.fieldname === "attendance_pct") {
            const pct = parseFloat(data.attendance_pct) || 0;
            const col = pct >= 95 ? "#27ae60"
                       : pct >= 85 ? "#2ecc71"
                       : pct >= 75 ? "#f39c12"
                       :             "#e74c3c";
            return `
              <div style="display:flex;align-items:center;gap:6px;">
                <div style="flex:1;height:8px;background:#eee;border-radius:4px;overflow:hidden;min-width:55px;">
                  <div style="width:${Math.min(pct,100)}%;height:100%;background:${col};border-radius:4px;"></div>
                </div>
                <span style="min-width:38px;font-size:12px;">${pct.toFixed(1)}%</span>
              </div>`;
        }

        // ── Day status pill (Daily Detail mode) ─────────────────────────
        if (column.fieldname === "day_status") {
            const map = {
                "Present":      "green",
                "Overtime":     "blue",
                "Late":         "orange",
                "Early Exit":   "orange",
                "Late + Early": "red",
                "Incomplete":   "red",
                "Absent":       "red",
            };
            const c = map[data.day_status] || "grey";
            return `<span class="indicator-pill ${c}">${data.day_status}</span>`;
        }

        // ── Highlight late arrivals in orange ────────────────────────────
        if (column.fieldname === "late_entry" && data.late_entry &&
            data.late_entry !== "On time" && data.late_entry !== "—") {
            return `<span style="color:#e67e22;font-weight:600;">${data.late_entry}</span>`;
        }

        // ── Highlight early exits in orange ──────────────────────────────
        if (column.fieldname === "early_exit" && data.early_exit &&
            data.early_exit !== "Normal" && data.early_exit !== "—") {
            return `<span style="color:#e67e22;font-weight:600;">${data.early_exit}</span>`;
        }

        // ── Highlight missing punches in red ─────────────────────────────
        if (column.fieldname === "missing_punch" && data.missing_punch &&
            data.missing_punch !== "—") {
            return `<span style="color:#e74c3c;font-weight:600;">${data.missing_punch}</span>`;
        }

        // ── Highlight high absent days ───────────────────────────────────
        if (column.fieldname === "absent_days") {
            const v = parseFloat(data.absent_days) || 0;
            if (v >= 3)
                return `<span style="color:#e74c3c;font-weight:600;">${v}</span>`;
        }

        // ── Highlight 3+ late entries in summary ────────────────────────
        if (column.fieldname === "late_entries") {
            const v = parseInt(data.late_entries) || 0;
            if (v >= 3)
                return `<span style="color:#e67e22;font-weight:600;">${v}</span>`;
        }

        // ── OT hours in blue when > 0 ────────────────────────────────────
        if (column.fieldname === "overtime_hours") {
            const v = parseFloat(data.overtime_hours) || 0;
            if (v > 0)
                return `<span style="color:#2980b9;font-weight:600;">${v.toFixed(1)}</span>`;
        }

        return value;
    },

    // ─── ON LOAD — quick date-range buttons ─────────────────────────────────
    onload(report) {
        report.page.add_inner_button(__("Today"), () => {
            const today = frappe.datetime.get_today();
            frappe.query_report.set_filter_value("from_date", today);
            frappe.query_report.set_filter_value("to_date",   today);
            frappe.query_report.refresh();
        });

        report.page.add_inner_button(__("This Week"), () => {
            frappe.query_report.set_filter_value("from_date", frappe.datetime.week_start());
            frappe.query_report.set_filter_value("to_date",   frappe.datetime.week_end());
            frappe.query_report.refresh();
        });

        report.page.add_inner_button(__("This Month"), () => {
            frappe.query_report.set_filter_value("from_date", frappe.datetime.month_start());
            frappe.query_report.set_filter_value("to_date",   frappe.datetime.month_end());
            frappe.query_report.refresh();
        });

        report.page.add_inner_button(__("Last Month"), () => {
            const last = frappe.datetime.add_months(frappe.datetime.month_start(), -1);
            frappe.query_report.set_filter_value("from_date", last);
            frappe.query_report.set_filter_value("to_date",   frappe.datetime.month_end(last));
            frappe.query_report.refresh();
        });
    },
};