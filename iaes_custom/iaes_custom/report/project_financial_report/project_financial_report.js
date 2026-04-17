frappe.query_reports["Project Financial Report"] = {
    filters: [
        { fieldname:"company",      label:__("Company"),             fieldtype:"Link",   options:"Company",  default:frappe.defaults.get_user_default("Company"), reqd:1 },
        { fieldname:"status",       label:__("Status"),              fieldtype:"Select", options:"\nOpen\nCompleted\nCancelled" },
        { fieldname:"customer",     label:__("Customer"),            fieldtype:"Link",   options:"Customer" },
        { fieldname:"project",      label:__("Project"),             fieldtype:"Link",   options:"Project" },
        { fieldname:"from_date",    label:__("Expected Start From"), fieldtype:"Date" },
        { fieldname:"to_date",      label:__("Expected End To"),     fieldtype:"Date" },
        { fieldname:"overdue_only", label:__("Overdue Only"),        fieldtype:"Check",  default:0 },
    ],
    onload(report) {
        report.page.add_inner_button(__("Sales Invoices"),    () => _open_list(report,"Sales Invoice",   "sales-invoice"),    __("View Documents"));
        report.page.add_inner_button(__("Purchase Invoices"), () => _open_list(report,"Purchase Invoice","purchase-invoice"), __("View Documents"));
        report.page.add_inner_button(__("Expense Claims"),    () => _open_list(report,"Expense Claim",   "expense-claim"),    __("View Documents"));
        report.page.add_inner_button(__("Stock Entries"),     () => _open_list(report,"Stock Entry",     "stock-entry"),      __("View Documents"));
        report.page.add_inner_button(__("Sales Orders"),      () => _open_list(report,"Sales Order",     "sales-order"),      __("View Documents"));
    },
    formatter(value, row, column, data, default_formatter) {
        if (!data) return default_formatter(value, row, column, data);
        value = default_formatter(value, row, column, data);
        const fn = column.fieldname;
        if (fn==="so_value"         && data.so_count   > 0) value = _link(value,"sales-order",      data.project,`${data.so_count} Sales Order(s)`);
        if (fn==="sinv_value"       && data.sinv_count > 0) value = _link(value,"sales-invoice",    data.project,`${data.sinv_count} Sales Invoice(s)`);
        if (fn==="sinv_paid"        && data.sinv_count > 0) value = _link(value,"sales-invoice",    data.project,"Collected – click to view");
        if (fn==="sinv_outstanding" && data.sinv_count > 0) value = _link(value,"sales-invoice",    data.project,"Outstanding – click to view",true);
        if (fn==="pinv_value"       && data.pinv_count > 0) value = _link(value,"purchase-invoice", data.project,`${data.pinv_count} Purchase Invoice(s)`);
        if (fn==="pinv_paid"        && data.pinv_count > 0) value = _link(value,"purchase-invoice", data.project,"Paid – click to view");
        if (fn==="pinv_outstanding" && data.pinv_count > 0) value = _link(value,"purchase-invoice", data.project,"Outstanding – click to view",true);
        if (fn==="exp_value"        && data.exp_count  > 0) value = _link(value,"expense-claim",    data.project,`${data.exp_count} Expense Claim(s)`);
        if (fn==="exp_paid"         && data.exp_count  > 0) value = _link(value,"expense-claim",    data.project,"Reimbursed – click to view");
        if (fn==="stock_value"      && data.ste_count  > 0) value = _link(value,"stock-entry",      data.project,`${data.ste_count} Stock Entry/Entries`);
        if (fn==="status") {
            const c={Open:"blue",Completed:"green",Cancelled:"red"}[data.status]||"gray";
            value=`<span class="badge badge-${c}" style="font-size:11px;padding:3px 8px">${data.status}</span>`;
        }
        if (fn==="days_remaining" && data.days_remaining!=null) {
            if (data.status==="Completed")    value=`<span style="color:var(--green-500)">&#10003; Done</span>`;
            else if (data.status==="Cancelled") value=`<span style="color:var(--text-muted)">N/A</span>`;
            else if (data.days_remaining<0)   value=`<span style="color:var(--red-500);font-weight:600">${Math.abs(data.days_remaining)}d overdue</span>`;
            else if (data.days_remaining<=14) value=`<span style="color:var(--red-400);font-weight:600">${data.days_remaining}d left</span>`;
            else if (data.days_remaining<=30) value=`<span style="color:var(--yellow-500);font-weight:500">${data.days_remaining}d left</span>`;
            else                              value=`<span style="color:var(--green-500)">${data.days_remaining}d left</span>`;
        }
        if (fn==="gross_margin") value=`<span style="color:${data.gross_margin<0?"var(--red-500)":"var(--green-600)"};font-weight:500">${value}</span>`;
        if (fn==="margin_pct")   value=`<span style="color:${data.margin_pct<0?"var(--red-500)":data.margin_pct<10?"var(--yellow-600)":"var(--green-600)"}">${value}</span>`;
        return value;
    },
};
function _link(display, slug, project, tip, outstanding) {
    if (!display || display==="0.00" || display==="0") return display;
    const enc=encodeURIComponent(project);
    const extra=outstanding?"&outstanding_amount=>0":"";
    const color=outstanding?"var(--red-400)":"var(--blue-500)";
    return `<a href="/app/${slug}?project=${enc}&docstatus=1${extra}" target="_blank" title="${tip}" style="text-decoration:underline;text-underline-offset:2px;color:${color}">${display}</a>`;
}
function _open_list(report, doctype_label, slug) {
    const rows=report.data;
    if (!rows||!rows.length){frappe.msgprint(__("Run the report first."));return;}
    const projects=[...new Set(rows.map(r=>r.project).filter(Boolean))];
    if (!projects.length) return;
    const url=projects.length===1
        ?`/app/${slug}?project=${encodeURIComponent(projects[0])}&docstatus=1`
        :`/app/${slug}?filters=${encodeURIComponent(JSON.stringify([[doctype_label,"project","in",projects],[doctype_label,"docstatus","=",1]]))}`;
    window.open(url,"_blank");
}