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
//     - (v5) sets the party account (Paid To / Paid From) from the supplied documents'
//       own payable/receivable account, so a wrong account on the form no longer
//       causes "Nothing matched"; stops with a clear message if the IDs span accounts
//     - (v6) for Employee parties, core ERPNext leaves the new-form default cash account
//       (Cash - IAES) in the party-side field. On Party / Payment Type change this now
//       moves that cash/bank account to the bank side and puts the company's Expense Claim
//       payable account on the party side. Only replaces a blank or Cash/Bank account.
//
// Touches no core method. Additive only -> upgrade safe.

const BUILD = "2026-11-09-v6";

// Where each pulled document keeps its party account (invoices path only;
// orders carry no party account, so they keep using whatever is on the form).
const IAES_ACCOUNT_SOURCE = {
        Employee: { doctype: "Expense Claim", field: "payable_account" },
        Supplier: { doctype: "Purchase Invoice", field: "credit_to" },
        Customer: { doctype: "Sales Invoice", field: "debit_to" },
};

frappe.ui.form.on("Payment Entry", {
        refresh(frm) {
                console.log("[iaes] payment_entry_pull_by_id build", BUILD);
                iaes_setup_pull_buttons(frm);
        },
        party_type(frm) {
                // Party Type can change after the form first renders; rebuild so the
                // dropdown reflects Employee (Expense Claims) vs Customer/Supplier.
                iaes_setup_pull_buttons(frm);
        },
        payment_type(frm) {
                iaes_setup_pull_buttons(frm);
                iaes_fix_employee_accounts(frm);
        },
        party(frm) {
                iaes_fix_employee_accounts(frm);
        },
});

// (v6) Wait for core's own party/payment_type calls to finish, then correct the accounts.
function iaes_fix_employee_accounts(frm) {
        frappe.after_ajax(() => iaes_fix_employee_accounts_now(frm));
}

async function iaes_fix_employee_accounts_now(frm) {
        const d = frm.doc;
        if (d.docstatus !== 0 || d.party_type !== "Employee" || !d.party || !d.company) return;
        if (!["Pay", "Receive"].includes(d.payment_type)) return;

        const party_field = d.payment_type === "Pay" ? "paid_to" : "paid_from";
        const bank_field = d.payment_type === "Pay" ? "paid_from" : "paid_to";

        const co = await frappe.db.get_value("Company", d.company,
                ["default_expense_claim_payable_account", "default_payable_account"]);
        const target = (co.message || {}).default_expense_claim_payable_account
                || (co.message || {}).default_payable_account;
        if (!target) return;

        const current = d[party_field];
        if (current === target) return;

        // Only replace a blank or a Cash/Bank account; leave a deliberate payable/advance account alone.
        let current_type = "";
        if (current) {
                const a = await frappe.db.get_value("Account", current, "account_type");
                current_type = (a.message || {}).account_type || "";
                if (!["Cash", "Bank"].includes(current_type)) return;
        }

        // Move the cash/bank account to the bank side if that side is empty.
        if (current && !frm.doc[bank_field]) {
                await frm.set_value(bank_field, current);
        }
        await frm.set_value(party_field, target);
        console.log("[iaes] employee accounts fixed:", party_field, current || "(blank)", "->", target,
                current && frm.doc[bank_field] === current ? "| " + bank_field + " = " + current : "");
}

function iaes_setup_pull_buttons(frm) {
        const grp = __("Pull by ID");

        // Always clear our own buttons first so a party-type change rebuilds cleanly
        // (remove_custom_button is a no-op when the button isn't present).
        ["Invoices by ID", "Orders by ID", "Expense Claims by ID"].forEach((lbl) => {
                frm.remove_custom_button(__(lbl), grp);
        });

        if (frm.doc.docstatus !== 0) return;
        const pt = frm.doc.party_type;
        if (!["Customer", "Supplier", "Employee"].includes(pt)) return;

        if (pt === "Employee") {
                // Employees: Expense Claims come through the "invoices" path. No orders apply.
                frm.add_custom_button(__("Expense Claims by ID"), () => iaes_prompt_pull(frm, "invoices"), grp);
        } else {
                frm.add_custom_button(__("Invoices by ID"), () => iaes_prompt_pull(frm, "invoices"), grp);
                frm.add_custom_button(__("Orders by ID"), () => iaes_prompt_pull(frm, "orders"), grp);
        }
}

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

function iaes_pull_example(frm, mode) {
        // A representative document name for the current party type + mode, so the
        // help text matches the label instead of always showing a Purchase Invoice.
        const pt = frm.doc.party_type;
        if (mode === "orders") {
                return pt === "Customer" ? "SAL-ORD-2026-00123" : "PUR-ORD-2026-00123";
        }
        if (pt === "Employee") return "HR-EXP-2026-00123";
        return pt === "Customer" ? "ACC-SINV-2026-00123" : "ACC-PINV-2026-00123";
}

function iaes_prompt_pull(frm, mode) {
        const label = iaes_pull_label(frm, mode);
        const example = iaes_pull_example(frm, mode);

        frappe.prompt(
                [
                        {
                                fieldtype: "Small Text",
                                fieldname: "ids",
                                label: label,
                                reqd: 1,
                                description: __(
                                        "Paste exact document names, one per line or comma-separated (e.g. {0}). Date range is ignored — all outstanding is searched.",
                                        [example]
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

        // (v5) Align the party account with the documents before searching.
        let account_note = "";
        if (mode === "invoices") {
                const res = await iaes_align_party_account(frm, wanted);
                if (res.stop) return;
                account_note = res.note || "";
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
                                "None of the supplied IDs are currently outstanding for {0} on account {1}.<br><br>Not found / fully paid: {2}",
                                [frm.doc.party, party_account, missing.join(", ")]
                        ) + (account_note ? "<br><br>" + account_note : ""),
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
        if (account_note) msg += "<br>" + account_note;
        let indicator = "green";
        if (missing.length) {
                msg += "<br>" + __("Not outstanding / not found: {0}", [missing.join(", ")]);
                indicator = "orange";
        }
        frappe.msgprint({ title: __("Pull by ID"), message: msg, indicator: indicator });
}

// (v5) Read the party account straight from the supplied documents and put it on the form.
// Returns { stop: true } if the caller must abort, otherwise { note: "<what changed>" }.
async function iaes_align_party_account(frm, wanted) {
        const src = IAES_ACCOUNT_SOURCE[frm.doc.party_type];
        if (!src) return {};

        let docs = [];
        try {
                docs = await frappe.db.get_list(src.doctype, {
                        filters: { name: ["in", wanted], docstatus: 1, company: frm.doc.company },
                        fields: ["name", src.field + " as account"],
                        limit: wanted.length,
                });
        } catch (e) {
                // Not fatal: fall back to whatever account is already on the form.
                console.warn("[iaes] pull_by_id account lookup failed", e);
                return {};
        }
        if (!docs.length) return {}; // nothing submitted found; the outstanding check will report it

        // Group IDs by account
        const by_acc = {};
        docs.forEach((d) => {
                if (!d.account) return;
                (by_acc[d.account] = by_acc[d.account] || []).push(d.name);
        });
        const accounts = Object.keys(by_acc);
        if (!accounts.length) return {};

        if (accounts.length > 1) {
                const lines = accounts.map((a) => "<b>" + a + "</b>: " + by_acc[a].join(", ")).join("<br>");
                frappe.msgprint({
                        title: __("Different party accounts"),
                        message: __("The supplied {0}s are booked to more than one account. Pay each account in a separate Payment Entry:", [src.doctype]) + "<br><br>" + lines,
                        indicator: "orange",
                });
                return { stop: true };
        }

        const target = accounts[0];
        const fieldname = frm.doc.payment_type === "Receive" ? "paid_from" : "paid_to";
        const current = frm.doc[fieldname];
        if (current === target) return {};

        await frm.set_value(fieldname, target);
        console.log("[iaes] pull_by_id set", fieldname, "from", current, "to", target);
        return {
                note: __("{0} changed from {1} to {2} to match the documents.", [
                        frappe.meta.get_label("Payment Entry", fieldname),
                        current || __("(blank)"),
                        target,
                ]),
        };
}