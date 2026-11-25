frappe.listview_settings["Costing Sheet"] = {
	add_fields: ["status", "error_count"],
	get_indicator(doc) {
		const colours = { Draft: "gray", Blocked: "red", Ready: "green", Quoted: "blue", Cancelled: "darkgrey" };
		return [__(doc.status), colours[doc.status] || "gray", "status,=," + doc.status];
	},
};
