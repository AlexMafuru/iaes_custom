// iaes_custom/public/js/payment_entry_pull_by_id.js
// Pull outstanding Purchase/Sales Invoices or Orders into Payment Entry by EXACT ID.
//
// Why this exists:
//   Core "Get Outstanding Invoices/Orders" forces a posting-date window (today-30 .. today)
//   and pulls everything in range, so the reference list often misses invoices and the
//   allocated total does not match the declared payment. This adds a "Pull by ID" path that:
//     - ignores any date window (pulls ALL outstanding for the party, then keeps only your IDs)
//     - reuses the stable core server method get_outstanding_reference_documents
//     - reuses the stable core allocator allocate_party_amount_against_ref_docs
//     - reports any IDs you pasted that are NOT actually outstanding (reconciliation gap)
//
// Touches no core method. Additive only -> upgrade safe.

const BUILD = "2026-06-25-v2";

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		console.log("[iaes] payment_entry_pull_by_id build", BUILD);

		if (frm.doc.docstatus !== 0) return;
		const pt = frm.doc.party_type;
		if (!["Customer", "Supplier", "Employee"].includes(pt)) return;

		const grp = __("Pull by ID");

		if (pt === "Employee") {
			// Employees: Expense Claims come through the "invoices" path. No orders apply.
			frm.add_custom_button(__("Expense Claims by ID"), () => iaes_prompt_pull(frm, "invoices"), grp);
		} else {
			frm.add_custom_button(__("Invoices by ID"), () => iaes_prompt_pull(frm, "invoices"), grp);
			frm.add_custom_button(__("Orders by ID"), () => iaes_prompt_pull(frm, "orders"), grp);
		}
	},
});

function iaes_parse_ids(raw) {
	// Accept newline, comma, semicolon or whitespace separated. Trim, drop blanks, dedupe.
	return [...new Set((raw || "").split(/[\n,;\s]+/).map((s) => s.trim()).filter(Boolean))];
}

function iaes_pull_label(frm, mode) {
	const pt = frm.doc.party_type;
	if (mode === "orders") {
		return pt === "Customer" ? __("Sales Order IDs") : __("Purchase Order IDs");
	}
	if (pt === "Employee") return __("Expense Claim IDs");
	return pt === "Customer" ? __("Sales Invoice IDs") : __("Purchase Invoice IDs");
}

function iaes_prompt_pull(frm, mode) {
	const label = iaes_pull_label(frm, mode);

	frappe.prompt(
		[
			{
				fieldtype: "Small Text",
				fieldname: "ids",
				label: label,
				reqd: 1,
				description: __(
					"Paste exact document names, one per line or comma-separated (e.g. ACC-PINV-2026-00123). Date range is ignored — all outstanding is searched."
				),
			},
			{
				fieldtype: "Check",
				fieldname: "clear_existing",
				label: __("Replace existing reference rows"),
				default: 1,
			},
			{
				fieldtype: "Check",
				fieldname: "allocate",
				label: __("Allocate Payment Amount"),
				default: 1,
			},
		],
		(values) => iaes_do_pull(frm, mode, values),
		__("Pull by ID"),
		__("Fetch")
	);
}

async function iaes_do_pull(frm, mode, values) {
	const wanted = iaes_parse_ids(values.ids);
	if (!wanted.length) {
		frappe.msgprint(__("No IDs supplied."));
		return;
	}

	if (!frm.doc.company || !frm.doc.party_type || !frm.doc.party) {
		frappe.msgprint(__("Please set Company, Party Type and Party first."));
		return;
	}

	const party_account = frm.doc.payment_type === "Receive" ? frm.doc.paid_from : frm.doc.paid_to;
	if (!party_account) {
		frappe.msgprint(__("Please set the party account (Paid From / Paid To) first."));
		return;
	}

	// Mirror core get_outstanding_documents args build -- but DO NOT pass any date filters,
	// so the server returns every outstanding document for the party regardless of date.
	const args = {
		posting_date: frm.doc.posting_date,
		company: frm.doc.company,
		party_type: frm.doc.party_type,
		payment_type: frm.doc.payment_type,
		party: frm.doc.party,
		party_account: party_account,
		cost_center: frm.doc.cost_center,
	};
	if (mode === "orders") {
		args.get_orders_to_be_billed = true;
	} else {
		args.get_outstanding_invoices = true;
	}
	if (frm.doc.book_advance_payments_in_separate_party_account) {
		args.book_advance_payments_in_separate_party_account = true;
	}

	frappe.flags.allocate_payment_amount = values.allocate ? true : false;

	let r;
	try {
		r = await frappe.call({
			method: "erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents",
			args: { args: args },
			freeze: true,
			freeze_message: __("Fetching outstanding documents…"),
		});
	} catch (e) {
		frappe.msgprint(__("Could not fetch outstanding documents. See console."));
		console.error("[iaes] pull_by_id call failed", e);
		return;
	}

	const rows = r.message || [];

	// Keep ALL rows whose voucher_no is in the wanted set (a voucher with payment terms
	// returns several rows -- one per term -- and we must keep every one of them).
	const wantedSet = new Set(wanted);
	const matched = rows.filter((d) => wantedSet.has(d.voucher_no));
	const foundNames = new Set(matched.map((d) => d.voucher_no));
	const missing = wanted.filter((n) => !foundNames.has(n));

	if (!matched.length) {
		frappe.msgprint({
			title: __("Nothing matched"),
			message: __(
				"None of the supplied IDs are currently outstanding for {0}.<br><br>Not found / fully paid: {1}",
				[frm.doc.party, missing.join(", ")]
			),
			indicator: "orange",
		});
		return;
	}

	// Optionally clear, then guard against duplicates when appending.
	if (values.clear_existing) {
		frm.clear_table("references");
	}
	const existing = new Set((frm.doc.references || []).map((c) => c.reference_name));

	const company_currency = frappe.get_doc(":Company", frm.doc.company).default_currency;
	const party_account_currency =
		frm.doc.payment_type === "Receive" ? frm.doc.paid_from_account_currency : frm.doc.paid_to_account_currency;
	const order_doctypes = frm.events.get_order_doctypes(frm);

	let total_positive = 0;
	let total_negative = 0;
	let added = 0;

	matched.forEach((d) => {
		if (existing.has(d.voucher_no)) return; // skip rows already on the form when appending
		const c = frm.add_child("references");
		c.reference_doctype = d.voucher_type;
		c.reference_name = d.voucher_no;
		c.due_date = d.due_date;
		c.total_amount = d.invoice_amount;
		c.outstanding_amount = d.outstanding_amount;
		c.bill_no = d.bill_no;
		c.payment_term = d.payment_term;
		c.payment_term_outstanding = d.payment_term_outstanding;
		c.allocated_amount = d.allocated_amount;
		c.account = d.account;
		c.exchange_rate = party_account_currency !== company_currency ? d.exchange_rate : 1;
		added += 1;

		if (!in_list(order_doctypes, d.voucher_type)) {
			if (flt(d.outstanding_amount) > 0) total_positive += flt(d.outstanding_amount);
			else total_negative += Math.abs(flt(d.outstanding_amount));
		}
	});

	frm.refresh_field("references");

	// Mirror core: seed paid/received amount only if the user has not already entered one.
	const is_pay_side =
		(frm.doc.payment_type === "Receive" && frm.doc.party_type === "Customer") ||
		(frm.doc.payment_type === "Pay" && frm.doc.party_type === "Supplier") ||
		(frm.doc.payment_type === "Pay" && frm.doc.party_type === "Employee");

	if (is_pay_side) {
		if (total_positive > total_negative && !frm.doc.paid_amount) {
			await frm.set_value("paid_amount", total_positive - total_negative);
		} else if (total_negative && total_positive < total_negative && !frm.doc.received_amount) {
			await frm.set_value("received_amount", total_negative - total_positive);
		}
	}

	// Re-run allocation through the stable core helper.
	await frm.events.allocate_party_amount_against_ref_docs(
		frm,
		frm.doc.payment_type === "Receive" ? frm.doc.paid_amount : frm.doc.received_amount,
		false
	);

	let msg = __("Added {0} reference row(s) for {1} voucher(s).", [added, foundNames.size]);
	let indicator = "green";
	if (missing.length) {
		msg += "<br>" + __("Not outstanding / not found: {0}", [missing.join(", ")]);
		indicator = "orange";
	}
	frappe.msgprint({ title: __("Pull by ID"), message: msg, indicator: indicator });
}
