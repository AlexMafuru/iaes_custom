// sales_invoice_list_utils.js
// Customer Summary dialog + Sales Totals panel for the Sales Invoice list view.
// Mirrors the Purchase Invoice (Supplier Summary / Purchase Totals) utilities.
//
// Register (recommended, scoped to this doctype only) in hooks.py:
//   doctype_list_js = {"Sales Invoice": "public/js/sales_invoice_list_utils.js"}
// (app_include_js also works, but doctype_list_js avoids site-wide loading.)

const BUILD = "2026-06-26-v2";

frappe.listview_settings = frappe.listview_settings || {};
frappe.listview_settings["Sales Invoice"] = frappe.listview_settings["Sales Invoice"] || {};

(function () {
	const SETTINGS = frappe.listview_settings["Sales Invoice"];
	const _prev_onload = SETTINGS.onload;

	// Fields we pull for every invoice in the current filter / selection.
	const FIELDS = [
		"name", "customer", "customer_name", "status", "project",
		"net_total", "base_net_total",
		"total_taxes_and_charges", "base_total_taxes_and_charges",
		"grand_total", "base_grand_total",
		"outstanding_amount", "conversion_rate",
		"posting_date", "due_date", "currency",
	];

	// ---- helpers ---------------------------------------------------------

	const money = (v) => format_currency(flt(v), "TZS");

	// outstanding_amount is in transaction currency; normalise to company (TZS).
	const base_outstanding = (r) => flt(r.outstanding_amount) * (flt(r.conversion_rate) || 1);

	function days_overdue(r) {
		if (flt(base_outstanding(r)) <= 0 || !r.due_date) return 0;
		const due = frappe.datetime.str_to_obj(r.due_date);
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		const diff = Math.floor((today - due) / 86400000);
		return diff > 0 ? diff : 0;
	}

	function aging_bucket(r) {
		const d = days_overdue(r);
		if (d <= 0) return "current";
		if (d <= 30) return "b1";
		if (d <= 60) return "b2";
		if (d <= 90) return "b3";
		return "b4";
	}

	// Pull all rows for the active scope. If rows are checked, use those only.
	function fetch_rows(listview) {
		const checked = listview.get_checked_items().map((d) => d.name);
		const filters = checked.length
			? [["Sales Invoice", "name", "in", checked]]
			: listview.get_filters_for_args();

		return frappe.db
			.get_list("Sales Invoice", { filters, fields: FIELDS, limit: 0, order_by: "customer_name asc" })
			.then((rows) => ({ rows: rows || [], scoped: checked.length > 0 }));
	}

	function csv_cell(v) {
		v = v == null ? "" : String(v);
		return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
	}

	// ====================================================================
	//  CUSTOMER SUMMARY
	// ====================================================================
	function show_customer_summary(listview) {
		fetch_rows(listview).then(({ rows, scoped }) => {
			// group by customer
			const map = {};
			rows.forEach((r) => {
				const key = r.customer || r.customer_name || "(blank)";
				if (!map[key]) {
					map[key] = {
						customer: r.customer_name || r.customer || "(blank)",
						invoices: 0, sinvs: [], projects: new Set(),
						grand: 0, outstanding: 0, overdue: 0,
					};
				}
				const g = map[key];
				g.invoices += 1;
				g.sinvs.push(r.name);
				if (r.project) g.projects.add(r.project);
				g.grand += flt(r.base_grand_total);
				g.outstanding += base_outstanding(r);
				if (days_overdue(r) > 0) g.overdue += base_outstanding(r);
			});

			let data = Object.values(map);
			data.sort((a, b) => b.outstanding - a.outstanding); // default: biggest debtor first

			const totals = data.reduce(
				(t, g) => {
					t.invoices += g.invoices;
					t.grand += g.grand;
					t.outstanding += g.outstanding;
					t.overdue += g.overdue;
					return t;
				},
				{ invoices: 0, grand: 0, outstanding: 0, overdue: 0 }
			);

			const render = (sort_key, dir) => {
				if (sort_key) {
					const m = dir === "asc" ? 1 : -1;
					data.sort((a, b) => {
						let av = a[sort_key], bv = b[sort_key];
						if (sort_key === "customer") return av.localeCompare(bv) * m;
						return (flt(av) - flt(bv)) * m;
					});
				}
				const body = data
					.map((g, i) => {
						const od = g.overdue > 0
							? `<span style="color:#c0392b;font-weight:600">${money(g.overdue)}</span>`
							: money(g.overdue);
						const sinv_links = g.sinvs
							.map((n) => `<a href="/app/sales-invoice/${encodeURIComponent(n)}" target="_blank">${frappe.utils.escape_html(n)}</a>`)
							.join(", ");
						const proj_links = [...g.projects]
							.map((p) => `<a href="/app/project/${encodeURIComponent(p)}" target="_blank">${frappe.utils.escape_html(p)}</a>`)
							.join(", ") || "—";
						return `<tr>
							<td style="text-align:center">${i + 1}</td>
							<td>${frappe.utils.escape_html(g.customer)}</td>
							<td style="text-align:center">${g.invoices}</td>
							<td style="font-size:11px">${sinv_links}</td>
							<td style="font-size:11px">${proj_links}</td>
							<td style="text-align:right">${money(g.grand)}</td>
							<td style="text-align:right">${money(g.outstanding)}</td>
							<td style="text-align:right">${od}</td>
						</tr>`;
					})
					.join("");

				const foot = `<tr style="font-weight:700;background:#f5f5f5;border-top:2px solid #ccc">
					<td></td><td>TOTAL (${data.length} customers)</td>
					<td style="text-align:center">${totals.invoices}</td>
					<td></td><td></td>
					<td style="text-align:right">${money(totals.grand)}</td>
					<td style="text-align:right">${money(totals.outstanding)}</td>
					<td style="text-align:right;color:#c0392b">${money(totals.overdue)}</td>
				</tr>`;

				return { body, foot };
			};

			const { body, foot } = render();

			const head_cell = (label, key, align) =>
				`<th data-sort="${key || ""}" style="text-align:${align || "left"};${key ? "cursor:pointer" : ""}">${label}${key ? ' <span style="opacity:.4">⇅</span>' : ""}</th>`;

			const html = `
				<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">
					<input type="text" class="form-control cust-search" placeholder="Filter customers…" style="max-width:240px">
					${scoped ? '<span style="color:#2980b9;font-size:12px">Showing selected rows only</span>' : ""}
				</div>
				<div style="max-height:60vh;overflow:auto;border:1px solid #e0e0e0;border-radius:6px">
				<table class="table table-bordered" style="margin:0;font-size:13px">
					<thead style="position:sticky;top:0;background:#fafafa;z-index:1">
						<tr>
							${head_cell("#")}
							${head_cell("Customer Name", "customer")}
							${head_cell("Invoices", "invoices", "center")}
							${head_cell("SINV(s)")}
							${head_cell("Project(s)")}
							${head_cell("Grand Total", "grand", "right")}
							${head_cell("Outstanding", "outstanding", "right")}
							${head_cell("Overdue", "overdue", "right")}
						</tr>
					</thead>
					<tbody class="cust-body">${body}</tbody>
					<tfoot class="cust-foot">${foot}</tfoot>
				</table>
				</div>`;

			const d = new frappe.ui.Dialog({
				title: `Customer Summary (${rows.length} Invoices)`,
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "area", options: html }],
				primary_action_label: "Refresh",
				primary_action() {
					d.hide();
					show_customer_summary(listview);
				},
			});

			d.show();
			const $w = d.$wrapper;

			// CSV (header + rows + total)
			const build_csv = () => {
				const head = ["#", "Customer", "Invoices", "SINV(s)", "Project(s)", "Grand Total", "Outstanding", "Overdue"];
				const lines = [head.map(csv_cell).join(",")];
				data.forEach((g, i) =>
					lines.push([i + 1, g.customer, g.invoices, g.sinvs.join(" "), [...g.projects].join(" "), g.grand.toFixed(2), g.outstanding.toFixed(2), g.overdue.toFixed(2)].map(csv_cell).join(","))
				);
				lines.push(["", "TOTAL", totals.invoices, "", "", totals.grand.toFixed(2), totals.outstanding.toFixed(2), totals.overdue.toFixed(2)].map(csv_cell).join(","));
				return lines.join("\n");
			};

			d.set_secondary_action_label("Copy CSV");
			d.set_secondary_action(() => {
				frappe.utils.copy_to_clipboard(build_csv());
				frappe.show_alert({ message: "Customer summary copied", indicator: "green" });
			});

			// add a Download CSV button next to footer
			const $dl = $('<button class="btn btn-default btn-sm" style="margin-left:8px">Download CSV</button>');
			$dl.on("click", () => {
				const blob = new Blob([build_csv()], { type: "text/csv" });
				const a = document.createElement("a");
				a.href = URL.createObjectURL(blob);
				a.download = `Customer_Summary_${frappe.datetime.get_today()}.csv`;
				a.click();
			});
			$w.find(".modal-footer .btn-modal-secondary").after($dl);

			// live search
			$w.find(".cust-search").on("input", function () {
				const q = this.value.toLowerCase();
				$w.find(".cust-body tr").each(function () {
					const name = $(this).find("td:nth-child(2)").text().toLowerCase();
					$(this).toggle(name.indexOf(q) !== -1);
				});
			});

			// sortable headers
			let cur = { key: "outstanding", dir: "desc" };
			$w.find("thead th[data-sort]").on("click", function () {
				const key = $(this).data("sort");
				if (!key) return;
				cur = { key, dir: cur.key === key && cur.dir === "desc" ? "asc" : "desc" };
				const out = render(cur.key, cur.dir);
				$w.find(".cust-body").html(out.body);
				$w.find(".cust-foot").html(out.foot);
				$w.find(".cust-search").trigger("input");
			});
		});
	}

	// ====================================================================
	//  SALES TOTALS (floating panel)
	// ====================================================================
	function show_sales_totals(listview) {
		$("#sales-totals-panel").remove();

		fetch_rows(listview).then(({ rows, scoped }) => {
			const t = {
				count: rows.length, net: 0, tax: 0, grand: 0, outstanding: 0,
				customers: new Set(), status: {},
				aging: { current: 0, b1: 0, b2: 0, b3: 0, b4: 0 },
			};
			rows.forEach((r) => {
				t.net += flt(r.base_net_total);
				t.tax += flt(r.base_total_taxes_and_charges);
				t.grand += flt(r.base_grand_total);
				t.outstanding += base_outstanding(r);
				if (r.customer) t.customers.add(r.customer);
				t.status[r.status] = (t.status[r.status] || 0) + 1;
				t.aging[aging_bucket(r)] += base_outstanding(r);
			});
			const paid = t.grand - t.outstanding;
			const avg = t.count ? t.grand / t.count : 0;
			const outPct = t.grand ? (t.outstanding / t.grand) * 100 : 0;

			const row = (label, val, color) =>
				`<tr><td style="padding:3px 0;color:#555">${label}</td>
				 <td style="padding:3px 0;text-align:right;font-weight:600;${color ? "color:" + color : ""}">${val}</td></tr>`;

			const statusChips = Object.keys(t.status)
				.sort()
				.map((s) => `<span style="display:inline-block;background:#eef;border-radius:10px;padding:1px 8px;margin:2px;font-size:11px">${s}: ${t.status[s]}</span>`)
				.join("");

			const agingRow = (label, val, c) =>
				`<tr><td style="padding:2px 0;color:#666;font-size:12px">${label}</td>
				 <td style="padding:2px 0;text-align:right;font-size:12px;${c ? "color:" + c : ""}">${money(val)}</td></tr>`;

			const html = `
			<div id="sales-totals-panel" style="position:fixed;top:120px;left:24px;z-index:1050;width:320px;
				background:#fff;border:1px solid #ddd;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.18);
				padding:14px 16px;font-size:13px">
				<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
					<b>📊 Sales Totals</b>
					<span style="cursor:pointer;font-size:18px;line-height:1" class="st-close">&times;</span>
				</div>
				<div style="color:#777;font-size:12px;margin-bottom:8px">
					${t.count} invoices${scoped ? " (selected)" : " in current filter"} · ${t.customers.size} customers
				</div>
				<table style="width:100%">
					${row("Net Total:", money(t.net))}
					${row("Tax / VAT:", money(t.tax))}
					${row("Grand Total:", money(t.grand))}
					${row("Paid:", money(paid), "#27ae60")}
					${row("Outstanding:", money(t.outstanding), "#c0392b")}
				</table>
				<hr style="margin:8px 0">
				<table style="width:100%">
					${row("Avg / Invoice:", money(avg))}
					${row("Outstanding %:", outPct.toFixed(1) + "%")}
				</table>
				<hr style="margin:8px 0">
				<div style="font-size:11px;color:#888;margin-bottom:4px">RECEIVABLES AGEING (outstanding)</div>
				<table style="width:100%">
					${agingRow("Not yet due", t.aging.current, "#16a085")}
					${agingRow("1–30 days", t.aging.b1)}
					${agingRow("31–60 days", t.aging.b2, "#e67e22")}
					${agingRow("61–90 days", t.aging.b3, "#d35400")}
					${agingRow("90+ days", t.aging.b4, "#c0392b")}
				</table>
				<hr style="margin:8px 0">
				<div>${statusChips}</div>
				<div style="margin-top:10px;text-align:right">
					<a href="#" class="st-copy" style="margin-right:12px">Copy all</a>
					<a href="#" class="st-refresh">Refresh</a>
				</div>
			</div>`;

			$("body").append(html);
			const $p = $("#sales-totals-panel");
			$p.find(".st-close").on("click", () => $p.remove());
			$p.find(".st-refresh").on("click", (e) => { e.preventDefault(); show_sales_totals(listview); });
			$p.find(".st-copy").on("click", (e) => {
				e.preventDefault();
				const lines = [
					`Sales Totals (${t.count} invoices, ${t.customers.size} customers)`,
					`Net Total: ${money(t.net)}`,
					`Tax/VAT: ${money(t.tax)}`,
					`Grand Total: ${money(t.grand)}`,
					`Paid: ${money(paid)}`,
					`Outstanding: ${money(t.outstanding)}  (${outPct.toFixed(1)}%)`,
					`Avg/Invoice: ${money(avg)}`,
					`Ageing — Not due: ${money(t.aging.current)} | 1-30: ${money(t.aging.b1)} | 31-60: ${money(t.aging.b2)} | 61-90: ${money(t.aging.b3)} | 90+: ${money(t.aging.b4)}`,
				];
				frappe.utils.copy_to_clipboard(lines.join("\n"));
				frappe.show_alert({ message: "Sales totals copied", indicator: "green" });
			});

			// drag to move (grab the header)
			let drag = null;
			$p.find("b").css("cursor", "move").on("mousedown", (e) => {
				drag = { x: e.clientX - $p[0].offsetLeft, y: e.clientY - $p[0].offsetTop };
				e.preventDefault();
			});
			$(document).on("mousemove.st", (e) => {
				if (!drag) return;
				$p.css({ left: e.clientX - drag.x + "px", top: e.clientY - drag.y + "px" });
			});
			$(document).on("mouseup.st", () => (drag = null));
		});
	}

	// ====================================================================
	//  WIRE UP
	// ====================================================================
	SETTINGS.onload = function (listview) {
		if (_prev_onload) _prev_onload(listview);
		console.log("[Sales Invoice utils] build", BUILD);

		listview.page.add_inner_button("Customer Summary", () => show_customer_summary(listview));
		listview.page.add_inner_button("Sales Totals", () => show_sales_totals(listview));
	};
})();
