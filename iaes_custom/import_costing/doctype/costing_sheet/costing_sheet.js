// Copyright (c) 2026, Alex and contributors
// Costing Sheet form. All calculation happens on the server when the sheet is saved.

const IAES_COSTING_BUILD = "import-costing 2026-11-25.1";
console.log("[IAES] Costing Sheet script loaded, build " + IAES_COSTING_BUILD);

frappe.ui.form.on("Costing Sheet", {
	setup(frm) {
		frm.set_query("award_override", "imported_items", (doc) => ({
			filters: { name: ["in", (doc.shipments || []).map((s) => s.supplier)] },
		}));
		frm.set_query("supplier", "offers", (doc) => ({
			filters: { name: ["in", (doc.shipments || []).map((s) => s.supplier)] },
		}));
		frm.set_query("supplier_quotation", "shipments", (doc) => ({
			filters: { opportunity: doc.opportunity, docstatus: ["<", 2] },
		}));
		frm.set_query("labour_rate", "labour_items", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		show_section_help(frm);
		if (frm.doc.__onload && frm.doc.__onload.checks_html !== undefined) {
			frm.get_field("checks_html").$wrapper.html(frm.doc.__onload.checks_html);
		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			if (frm.doc.quotation_type !== "Installation only") {
				frm.add_custom_button(__("Items from Opportunity"), () => run(frm, "get_opportunity_items",
					{}, (n) => __("{0} item(s) added", [n])), __("Get"));
				frm.add_custom_button(__("Supplier Quotations"), () => run(frm, "get_supplier_quotations",
					{}, (n) => __("{0} Supplier Quotation(s) added", [n])), __("Get"));
			}
			frm.add_custom_button(__("Installation Template"), () => apply_template(frm), __("Get"));
			// mark dirty first: otherwise Frappe skips the save ("No changes in document")
			// and new rates in Costing Settings are never picked up
			frm.add_custom_button(__("Recalculate"), () => {
				frm.dirty();
				frm.save();
			});
		}
		if (frm.doc.docstatus === 1 && !frm.doc.quotation) {
			frm.add_custom_button(__("Quotation"), () => make_quotation(frm), __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
		if (frm.doc.quotation) {
			frm.add_custom_button(__("Open Quotation"), () => frappe.set_route("Form", "Quotation", frm.doc.quotation));
		}
		frm.set_df_property("override_approved", "read_only",
			!frappe.user.has_role(frm.doc.__onload?.approver_role || "Sales Manager"));
	},

	quotation_type: show_section_help,
});

function show_section_help(frm) {
	const map = {
		"Supply only": __("Sections A (imported), B (local) and E (other) are costed."),
		"Supply & Installation": __("All sections A to E are costed."),
		"Installation only": __("Sections B (optional local goods), C (labour), D (site) and E (other) are costed."),
	};
	if (frm.doc.error_count) {
		frm.dashboard.set_headline(
			__("{0} blocking check(s) - see the Summary tab.", [frm.doc.error_count]), "red");
	} else if (frm.doc.quotation_type) {
		frm.dashboard.set_headline(map[frm.doc.quotation_type] || "", "blue");
	}
}

function run(frm, method, args, msg) {
	const go = () => frm.call({ doc: frm.doc, method, args, freeze: true }).then((r) => {
		frm.reload_doc();
		frappe.show_alert({ message: msg(r.message || 0), indicator: "green" });
	});
	frm.is_dirty() ? frm.save().then(go) : go();
}

function apply_template(frm) {
	const groups = (frm.doc.selling_groups || []).map((g) => g.group_name);
	const d = new frappe.ui.Dialog({
		title: __("Apply Installation Template"),
		fields: [
			{ fieldname: "template", fieldtype: "Link", options: "Installation Template", label: __("Template"), reqd: 1 },
			{ fieldname: "selling_group", fieldtype: "Autocomplete", options: groups, label: __("Selling Group (optional)"),
				description: __("Put the rows inside a selling line, e.g. the box they belong to.") },
		],
		primary_action_label: __("Apply"),
		primary_action(v) {
			d.hide();
			run(frm, "apply_installation_template", v, (n) => __("{0} row(s) added", [n]));
		},
	});
	d.show();
}

function make_quotation(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Make Quotation"),
		fields: [{
			fieldname: "mode", fieldtype: "Select", label: __("Layout"), options: "Grouped\nItemised", default: "Grouped",
			description: __("Grouped: rows with a Selling Group become one line per group. Itemised: every goods row is its own line. Labour and site costs outside a group are one lump-sum line."),
		}],
		primary_action_label: __("Create"),
		primary_action(v) {
			d.hide();
			frappe.call({
				method: "iaes_custom.import_costing.doctype.costing_sheet.costing_sheet.make_quotation",
				args: { source_name: frm.doc.name, mode: v.mode },
				freeze: true,
			}).then((r) => r.message && frappe.set_route("Form", "Quotation", r.message));
		},
	});
	d.show();
}

// keep qty in view while typing; everything else recalculates on save
frappe.ui.form.on("Costing Imported Item", {
	qty_per_set(frm, cdt, cdn) {
		const r = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "qty", flt(r.qty_per_set) * flt(frm.doc.sets || 1));
	},
});

frappe.ui.form.on("Costing Labour Item", {
	people: labour_amount, days: labour_amount, day_rate: labour_amount,
});

function labour_amount(frm, cdt, cdn) {
	const r = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(r.people) * flt(r.days) * flt(r.day_rate));
}
