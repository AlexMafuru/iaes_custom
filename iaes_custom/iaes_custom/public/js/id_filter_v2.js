(function () {
	function get_current_listview() {
		try {
			if (window.cur_list && cur_list.doctype && cur_list.page) {
				return cur_list;
			}
		} catch (e) {}
		return null;
	}

	function ensure_id_buttons(listview) {
		if (!listview || !listview.doctype || !listview.page) return;

		const doctype = listview.doctype;
		const beforeId = `iaes-id-before-btn-${doctype.replace(/\s+/g, "-")}`;
		const afterId = `iaes-id-after-btn-${doctype.replace(/\s+/g, "-")}`;

		if (document.getElementById(beforeId) || document.getElementById(afterId)) {
			return;
		}

		let target = null;

		try {
			if (listview.page.btn_primary && listview.page.btn_primary.parent && listview.page.btn_primary.parent().length) {
				target = listview.page.btn_primary.parent();
			}
		} catch (e) {}

		if (!target || !target.length) {
			try {
				const pageActions = listview.page.wrapper.find(".page-actions");
				if (pageActions && pageActions.length) {
					target = pageActions;
				}
			} catch (e) {}
		}

		if (!target || !target.length) return;

		const beforeBtn = $(`
			<button class="btn btn-default btn-sm ellipsis" id="${beforeId}" style="margin-right:8px;">
				ID Before
			</button>
		`);

		const afterBtn = $(`
			<button class="btn btn-default btn-sm ellipsis" id="${afterId}" style="margin-right:8px;">
				ID After
			</button>
		`);

		beforeBtn.on("click", function () {
			const d = new frappe.ui.Dialog({
				title: __("Filter ID Before"),
				fields: [
					{
						label: __("Document ID"),
						fieldname: "doc_id",
						fieldtype: "Data",
						reqd: 1,
						description: __("Applies filter: ID < entered value")
					}
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					listview.filter_area.add([
						[listview.doctype, "name", "<", values.doc_id]
					]);
					d.hide();
				}
			});
			d.show();
		});

		afterBtn.on("click", function () {
			const d = new frappe.ui.Dialog({
				title: __("Filter ID After"),
				fields: [
					{
						label: __("Document ID"),
						fieldname: "doc_id",
						fieldtype: "Data",
						reqd: 1,
						description: __("Applies filter: ID > entered value")
					}
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					listview.filter_area.add([
						[listview.doctype, "name", ">", values.doc_id]
					]);
					d.hide();
				}
			});
			d.show();
		});

		target.before(afterBtn);
		target.before(beforeBtn);
	}

	function try_attach_buttons() {
		const listview = get_current_listview();
		if (!listview) return;

		ensure_id_buttons(listview);
	}

	function start_global_id_buttons() {
		try_attach_buttons();

		let lastRoute = frappe.get_route_str ? frappe.get_route_str() : "";
		setInterval(() => {
			const currentRoute = frappe.get_route_str ? frappe.get_route_str() : "";
			if (currentRoute !== lastRoute) {
				lastRoute = currentRoute;
				setTimeout(try_attach_buttons, 400);
				setTimeout(try_attach_buttons, 1000);
			} else {
				try_attach_buttons();
			}
		}, 1200);

		if (frappe.after_ajax) {
			frappe.after_ajax(() => {
				setTimeout(try_attach_buttons, 300);
			});
		}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", start_global_id_buttons);
	} else {
		start_global_id_buttons();
	}
})();
