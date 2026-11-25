// Copyright (c) 2026, Alex and contributors
frappe.ui.form.on("Costing Settings", {
	refresh(frm) {
		frm.set_intro(
			__("Rates here are used by every new Costing Sheet calculation. Verify statutory rates and exchange rates before each quotation.")
		);
	},
});

frappe.ui.form.on("Costing Exchange Rate", {
	rate: (frm, cdt, cdn) => set_rate_used(cdt, cdn),
	buffer_pct: (frm, cdt, cdn) => set_rate_used(cdt, cdn),
});

function set_rate_used(cdt, cdn) {
	const r = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "rate_used", flt(r.rate) * (1 + flt(r.buffer_pct) / 100));
}
