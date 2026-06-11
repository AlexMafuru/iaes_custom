// iaes_custom :: Shared Floating List-View Calculator
// One file for ALL modules. Add a doctype by adding one entry to CALC_CONFIG.
// Loaded globally via app_include_js in hooks.py (no per-doctype Client Script needed).
//
//   app_include_js = [
//       "/assets/iaes_custom/js/listview_calculator.js",
//   ]
//
// After deploying, DELETE the old per-doctype Client Scripts
// (CustomScript0002/0003/0005/0006/0007 etc.) so the button isn't injected twice.

frappe.provide("iaes");

iaes.list_calculator = (function () {

    const BUILD = "2026-06-11-v8";
    console.log("[IAES list calculator] build", BUILD, "loaded");

    // Remembers where the user dragged the panel (viewport px). Null = default corner.
    let last_pos = null;

    // Keep a value within [min, max].
    function clamp(v, min, max) {
        return Math.max(min, Math.min(max, v));
    }

    // Keep the panel fully on screen given its current size.
    function clamp_to_viewport(left, top) {
        const $p = $('#iaes-calc-panel');
        const w = $p.outerWidth()  || 330;
        const h = $p.outerHeight() || 220;
        return {
            left: clamp(left, 4, window.innerWidth  - w - 4),
            top:  clamp(top,  4, window.innerHeight - h - 4)
        };
    }

    function apply_pos($p) {
        if (last_pos) {
            const c = clamp_to_viewport(last_pos.left, last_pos.top);
            $p.css({ left: c.left + "px", top: c.top + "px", right: "auto", bottom: "auto" });
        }
    }

    // Copy text with a fallback for non-HTTPS / blocked-clipboard cases.
    function copy_text(text) {
        const done = () => frappe.show_alert({ message: __("Copied"), indicator: "green" }, 1);
        const fail = () => frappe.show_alert({ message: __("Copy failed — select and copy manually"), indicator: "red" }, 3);
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done).catch(() => fallback());
            } else {
                fallback();
            }
        } catch (e) {
            fallback();
        }
        function fallback() {
            try {
                const ta = document.createElement("textarea");
                ta.value = text;
                ta.style.position = "fixed";
                ta.style.opacity = "0";
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                done();
            } catch (e2) {
                fail();
            }
        }
    }

    // -------------------------------------------------------------------
    // CONFIG — one entry per list view. label = display, field = docfield.
    // color "red"/"green" optional.
    // Add  use_base: true  to a doctype entry to total in COMPANY currency
    // (uses base_net_total, base_grand_total, etc.) — useful for lists that
    // mix foreign-currency documents. Default totals in document currency.
    // -------------------------------------------------------------------
    const CALC_CONFIG = {
        "Quotation": {
            title: "Quotation Totals",
            rows: [
                { label: "Net Total",   field: "net_total" },
                { label: "Grand Total", field: "grand_total" }
            ]
        },
        "Sales Order": {
            title: "Sales Order Totals",
            rows: [
                { label: "Net Total",   field: "net_total" },
                { label: "Grand Total", field: "grand_total" }
            ]
        },
        "Sales Invoice": {
            title: "Sales Invoice Totals",
            rows: [
                { label: "Net Total",    field: "net_total" },
                { label: "Grand Total",  field: "grand_total" },
                { label: "Outstanding",  field: "outstanding_amount", color: "red" }
            ]
        },
        "Purchase Order": {
            title: "Purchase Order Totals",
            rows: [
                { label: "Net Total",   field: "net_total" },
                { label: "Grand Total", field: "grand_total" }
            ]
        },
        "Expense Claim": {
            title: "Expense Claim Totals",
            rows: [
                { label: "Claimed",    field: "total_claimed_amount" },
                { label: "Sanctioned", field: "total_sanctioned_amount" },
                { label: "Reimbursed", field: "total_amount_reimbursed", color: "green" }
            ]
        }
        // "Purchase Invoice" is intentionally left out — it already has its own
        // Supplier Summary / Purchase Totals utilities. Add it here if you want
        // the floating button there too.
    };

    // The field used for the "Avg / doc" line (falls back to first row field).
    function avg_field(cfg) {
        const has = cfg.rows.find(r => r.field === "grand_total");
        return has ? "grand_total" : cfg.rows[0].field;
    }

    // -------------------------------------------------------------------
    // BUTTON + PANEL injection (shared across every configured doctype)
    // -------------------------------------------------------------------
    function ensure_button() {
        const $b = $('#iaes-calc-btn');
        if ($b.length && $b.attr('data-build') === BUILD) return;   // already current; just keep it
        $b.remove();   // missing or from an older build -> rebuild once

        $('body').append(`
            <div id="iaes-calc-btn" data-build="${BUILD}" title="Totals"
                 style="position:fixed; bottom:20px; right:20px; width:48px; height:48px;
                        border-radius:10px; background:#4361ee; display:none;
                        align-items:center; justify-content:center;
                        cursor:pointer; z-index:1029; box-shadow:var(--shadow-lg);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" style="display:block;"
                     stroke="#ffffff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="2" width="16" height="20" rx="2.5"></rect>
                    <rect x="7" y="5" width="10" height="3.5" rx="0.5" fill="#ffffff" stroke="none"></rect>
                    <line x1="8"  y1="12" x2="8"  y2="12"></line>
                    <line x1="12" y1="12" x2="12" y2="12"></line>
                    <line x1="16" y1="12" x2="16" y2="12"></line>
                    <line x1="8"  y1="15.5" x2="8"  y2="15.5"></line>
                    <line x1="12" y1="15.5" x2="12" y2="15.5"></line>
                    <line x1="16" y1="15.5" x2="16" y2="15.5"></line>
                    <line x1="8"  y1="19" x2="8"  y2="19"></line>
                    <line x1="12" y1="19" x2="12" y2="19"></line>
                    <line x1="16" y1="19" x2="16" y2="19"></line>
                </svg>
            </div>
        `);

        $('#iaes-calc-btn').on('click', function () {
            if ($('#iaes-calc-panel').length && $('#iaes-calc-panel').is(':visible')) {
                $('#iaes-calc-panel').hide();
            } else {
                calculate();
            }
        });
    }

    function active() {
        // cur_list is Frappe's global handle to the current list view
        const lv = (typeof cur_list !== "undefined") ? cur_list : null;
        if (!lv || !CALC_CONFIG[lv.doctype]) return null;
        return { lv: lv, doctype: lv.doctype, cfg: CALC_CONFIG[lv.doctype] };
    }

    // Show the button only on configured list views; hide everywhere else.
    function toggle_for_route() {
        const route = frappe.get_route() || [];
        const on_list = route[0] === "List" && CALC_CONFIG[route[1]];
        ensure_button();
        if (on_list) { show_button(); } else { $('#iaes-calc-btn').hide(); $('#iaes-calc-panel').hide(); }
    }

    // Always reveal with full flex centering so the icon can never drift to a corner.
    function show_button() {
        $('#iaes-calc-btn').css({ display: 'flex', alignItems: 'center', justifyContent: 'center' });
    }

    // -------------------------------------------------------------------
    // CALCULATION
    // -------------------------------------------------------------------
    function calculate() {
        const ctx = active();
        if (!ctx) return;

        const { lv, doctype, cfg } = ctx;
        const currency = frappe.defaults.get_global_default('currency');

        // When use_base is set, total the company-currency fields (base_net_total, base_grand_total, ...)
        const resolve = f => cfg.use_base ? ("base_" + f) : f;
        const display_fields = cfg.rows.map(r => resolve(r.field));
        const fields = [...new Set(display_fields.concat([resolve(avg_field(cfg))]))];

        const base_filters = lv.filter_area.get() || [];
        const checked = (lv.get_checked_items ? lv.get_checked_items(true) : []) || [];
        let filters = base_filters.slice();
        if (checked.length) filters.push([doctype, "name", "in", checked]);

        ensure_panel(cfg, doctype);   // build only if missing or doctype changed (keeps drag position)
        $('#iaes-calc-panel').show();
        $('#iaes-calc-count').text(__("Calculating..."));

        frappe.call({
            method: "frappe.client.get_list",
            args: { doctype: doctype, fields: fields, filters: filters, limit_page_length: 5000 },
            error: function () {
                $('#iaes-calc-count').text(__("Calculation failed — try Refresh."));
                frappe.show_alert({ message: __("Could not calculate totals"), indicator: "red" }, 5);
            },
            callback: function (r) {
                const data = r.message || [];

                if (data.length >= 5000) {
                    frappe.show_alert({
                        message: __("Showing first 5000 records only — totals may be incomplete"),
                        indicator: "orange"
                    }, 6);
                }

                const sums = {};
                fields.forEach(f => sums[f] = 0);
                data.forEach(d => fields.forEach(f => sums[f] += flt(d[f])));

                const label = checked.length
                    ? __("{0} selected", [data.length])
                    : __("{0} in current filter", [data.length]);
                $('#iaes-calc-count').html(
                    (checked.length ? `<span style="color:var(--primary-color);font-weight:bold;">● </span>` : ``) + label
                );

                cfg.rows.forEach((row, i) => {
                    const f = resolve(row.field);
                    const formatted = format_currency(sums[f], currency);
                    $(`#iaes-calc-val-${i}`).text(formatted).attr('data-raw', sums[f]);
                });

                const af = resolve(avg_field(cfg));
                const avg = data.length ? sums[af] / data.length : 0;
                $('#iaes-calc-avg').text(format_currency(avg, currency));
            }
        });
    }

    // -------------------------------------------------------------------
    // PANEL — built once per doctype. ensure_panel() keeps the existing
    // panel (and its dragged position) when the doctype hasn't changed,
    // so Refresh only updates the numbers in place.
    // -------------------------------------------------------------------
    function ensure_panel(cfg, doctype) {
        const $existing = $('#iaes-calc-panel');
        if ($existing.length && $existing.attr('data-doctype') === doctype) {
            apply_pos($existing);   // keep wherever the user dragged it
            return;
        }
        $existing.remove();
        build_panel(cfg, doctype);
        apply_pos($('#iaes-calc-panel'));   // restore dragged position even after a rebuild
    }

    function build_panel(cfg, doctype) {

        let rows_html = cfg.rows.map((row, i) => {
            const colorStyle = row.color === "red"   ? "color:var(--red-600);"
                             : row.color === "green" ? "color:var(--green-600);" : "";
            return `
                <div class="pi-row" style="margin-bottom:8px; display:flex; justify-content:space-between;">
                    <span>${frappe.utils.escape_html(row.label)}:</span>
                    <span style="font-weight:bold; ${colorStyle}">
                        <span id="iaes-calc-val-${i}"></span>
                        <i class="fa fa-copy iaes-copy" data-target="iaes-calc-val-${i}"
                           style="cursor:pointer; margin-left:5px; color:#ccc; font-size:12px;"></i>
                    </span>
                </div>`;
        }).join('');

        $('body').append(`
            <div id="iaes-calc-panel" data-doctype="${frappe.utils.escape_html(doctype)}" style="position:fixed; bottom:80px; right:20px; width:330px;
                 background:white; border-radius:8px; border:1px solid #d1d8dd;
                 box-shadow:var(--shadow-lg); z-index:1030; font-family:inherit;">
                <div class="iaes-calc-header" style="padding:10px 15px; background:var(--bg-light-gray);
                     font-weight:bold; display:flex; justify-content:space-between; cursor:move;
                     border-bottom:1px solid #d1d8dd;">
                    <span><i class="fa fa-calculator text-muted"></i> &nbsp; ${frappe.utils.escape_html(cfg.title)}</span>
                    <span class="iaes-calc-close" style="cursor:pointer">&times;</span>
                </div>
                <div style="padding:15px">
                    <div id="iaes-calc-count" style="font-size:11px; color:var(--text-muted); margin-bottom:12px;"></div>
                    ${rows_html}
                    <hr style="margin:12px 0;">
                    <div class="pi-row" style="display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted);">
                        <span>Avg / doc:</span>
                        <span><span id="iaes-calc-avg"></span></span>
                    </div>
                </div>
                <div style="padding:8px 15px; border-top:1px solid #f0f0f0; display:flex;
                     justify-content:space-between; font-size:11px;">
                    <span class="text-muted"><i class="fa fa-arrows"></i> Drag to move</span>
                    <span>
                        <span class="iaes-calc-copyall" style="cursor:pointer; color:var(--text-muted); margin-right:12px;">Copy all</span>
                        <span class="iaes-calc-refresh" style="cursor:pointer; color:var(--primary-color); font-weight:bold;">Refresh</span>
                    </span>
                </div>
            </div>
        `);

        const $panel = $('#iaes-calc-panel');

        $panel.find('.iaes-calc-header').on('mousedown', function (e) {
            const rect = $panel[0].getBoundingClientRect();
            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;
            e.preventDefault();
            $(document).on('mousemove.iaes-drag', function (ev) {
                const c = clamp_to_viewport(ev.clientX - offsetX, ev.clientY - offsetY);
                $panel.css({ left: c.left + "px", top: c.top + "px", right: "auto", bottom: "auto" });
                last_pos = { left: c.left, top: c.top };   // remember for next refresh / reopen
            }).on('mouseup.iaes-drag', function () {
                $(document).off('mousemove.iaes-drag mouseup.iaes-drag');
            });
        });

        $panel.find('.iaes-calc-close').on('click', () => $panel.hide());
        $panel.find('.iaes-calc-refresh').on('click', () => calculate());

        $panel.on('click', '.iaes-copy', function () {
            copy_text($(`#${$(this).data('target')}`).attr('data-raw'));
        });

        $panel.find('.iaes-calc-copyall').on('click', () => {
            const lines = [$('#iaes-calc-count').text()];
            cfg.rows.forEach((row, i) => lines.push(`${row.label}: ${$(`#iaes-calc-val-${i}`).text()}`));
            lines.push(`Avg / doc: ${$('#iaes-calc-avg').text()}`);
            copy_text(lines.join('\n'));
        });
    }

    // -------------------------------------------------------------------
    // WIRING — register every configured doctype + react to route changes
    // -------------------------------------------------------------------
    Object.keys(CALC_CONFIG).forEach(dt => {
        const existing = frappe.listview_settings[dt] || {};
        const prev_onload = existing.onload;
        existing.onload = function (listview) {
            if (prev_onload) prev_onload(listview);   // preserve any other script's onload
            ensure_button();
            show_button();
        };
        frappe.listview_settings[dt] = existing;
    });

    frappe.router.on('change', () => toggle_for_route());

    return { calculate, toggle_for_route };
})();