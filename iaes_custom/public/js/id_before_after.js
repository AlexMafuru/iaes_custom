(function() {
    frappe.provide("iaes_custom.id_filters");

    iaes_custom.id_filters.add_buttons = function (listview) {
        if (!listview || !listview.page || listview.page.__id_before_after_added) return;
        listview.page.__id_before_after_added = true;

        // Add "ID Before" to the Actions menu
        listview.page.add_action_item(__("ID Before"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Filter by ID Before"),
                fields: [{
                    label: __("Document ID"),
                    fieldname: "doc_id",
                    fieldtype: "Data",
                    reqd: 1,
                    description: __("Example: PINV-2026-0050")
                }],
                primary_action_label: __("Apply Filter"),
                primary_action(values) {
                    listview.filter_area.add([
                        [listview.doctype, "name", "<", values.doc_id],
                    ]);
                    d.hide();
                }
            });
            d.show();
        });

        // Add "ID After" to the Actions menu
        listview.page.add_action_item(__("ID After"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Filter by ID After"),
                fields: [{
                    label: __("Document ID"),
                    fieldname: "doc_id",
                    fieldtype: "Data",
                    reqd: 1,
                    description: __("Example: PINV-2026-0010")
                }],
                primary_action_label: __("Apply Filter"),
                primary_action(values) {
                    listview.filter_area.add([
                        [listview.doctype, "name", ">", values.doc_id],
                    ]);
                    d.hide();
                }
            });
            d.show();
        });
    };

    // Hook into ListView to add buttons on load
    $(document).on("app_ready", function () {
        if (!frappe.views || !frappe.views.ListView) return;

        const original_render = frappe.views.ListView.prototype.render;
        if (frappe.views.ListView.prototype._iaes_id_filter_patched) return;
        frappe.views.ListView.prototype._iaes_id_filter_patched = true;

        frappe.views.ListView.prototype.render = function () {
            const result = original_render.apply(this, arguments);
            setTimeout(() => {
                iaes_custom.id_filters.add_buttons(this);
            }, 500);
            return result;
        };
    });
})();
