frappe.listview_settings["Customer Visit"] = {
    add_fields: ["status", "visit_date", "assigned_to", "visit_outcome"],
    filters: [["status", "!=", "Cancelled"]],

    get_indicator(doc) {
        if (doc.status === "Closed") {
            return [__("Closed"), "green", "status,=,Closed"];
        }
        if (doc.status === "Cancelled") {
            return [__("Cancelled"), "gray", "status,=,Cancelled"];
        }
        if (doc.visit_date < frappe.datetime.get_today()) {
            // Derived, never stored as a status - see design note B/A1.
            return [__("Overdue"), "red", "status,=,Open|visit_date,<,Today"];
        }
        if (doc.status === "In Progress") {
            return [__("In Progress"), "orange", "status,=,In Progress"];
        }
        if (doc.visit_date === frappe.datetime.get_today()) {
            return [__("Due Today"), "blue", "visit_date,=,Today"];
        }
        return [__("Open"), "blue", "status,=,Open"];
    },
};
