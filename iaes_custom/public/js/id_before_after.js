(function () {
	function add_id_filter_buttons(listview) {
		if (!listview || !listview.page) return;
		if (listview.page.__id_before_after_added) return;
		listview.page.__id_before_after_added = true;

		listview.page.add_inner_button(__("ID Before"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Filter by ID Before"),
				fields: [
					{
						label: __("Document ID"),
						fieldname: "doc_id",
						fieldtype: "Data",
						reqd: 1,
					},
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					listview.filter_area.add([
						[listview.doctype, "name", "<", values.doc_id],
					]);
					d.hide();
				},
			});
			d.show();
		});

		listview.page.add_inner_button(__("ID After"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Filter by ID After"),
				fields: [
					{
						label: __("Document ID"),
						fieldname: "doc_id",
						fieldtype: "Data",
						reqd: 1,
					},
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					listview.filter_area.add([
						[listview.doctype, "name", ">", values.doc_id],
					]);
					d.hide();
				},
			});
			d.show();
		});
	}

	function patch_listview() {
		if (!frappe.views || !frappe.views.ListView) return;

		const proto = frappe.views.ListView.prototype;
		if (proto._iaes_id_buttons_patched) return;
		proto._iaes_id_buttons_patched = true;

		const original_show = proto.show;

		proto.show = function () {
			const result = original_show.apply(this, arguments);
			setTimeout(() => add_id_filter_buttons(this), 500);
			return result;
		};
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", patch_listview);
	} else {
		patch_listview();
	}
})();
