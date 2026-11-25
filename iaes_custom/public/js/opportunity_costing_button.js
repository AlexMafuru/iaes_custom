// Import Costing: "Create > Costing Sheet" on the Opportunity
console.log("[IAES] Opportunity costing button, build import-costing 2026-11-25.1");

frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status === "Lost") return;
		frm.add_custom_button(__("Costing Sheet"), () => {
			frappe.new_doc("Costing Sheet", {
				opportunity: frm.doc.name,
				company: frm.doc.company,
			});
		}, __("Create"));
		frappe.db.count("Costing Sheet", { filters: { opportunity: frm.doc.name, docstatus: ["<", 2] } }).then((n) => {
			if (n) {
				frm.add_custom_button(__("Costing Sheets ({0})", [n]), () =>
					frappe.set_route("List", "Costing Sheet", { opportunity: frm.doc.name }), __("View"));
			}
		});
	},
});
