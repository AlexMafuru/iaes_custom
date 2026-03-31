(function () {
    const add_id_filter_group = (listview) => {
        if (!listview || !listview.page || listview.page.__id_filters_added) return;
        listview.page.__id_filters_added = true;

        // Create a single dropdown menu called "ID Filters"
        // This will appear after the "List View" button
        listview.page.add_inner_button(__("Before"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Filter: ID Before"),
                fields: [{ label: __("Document ID"), fieldname: "doc_id", fieldtype: "Data", reqd: 1 }],
                primary_action_label: __("Apply"),
                primary_action(values) {
                    listview.filter_area.add([[listview.doctype, "name", "<", values.doc_id]]);
                    d.hide();
                }
            });
            d.show();
        }, __("ID Filters")); // Grouping name

        listview.page.add_inner_button(__("After"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Filter: ID After"),
                fields: [{ label: __("Document ID"), fieldname: "doc_id", fieldtype: "Data", reqd: 1 }],
                primary_action_label: __("Apply"),
                primary_action(values) {
                    listview.filter_area.add([[listview.doctype, "name", ">", values.doc_id]]);
                    d.hide();
                }
            });
            d.show();
        }, __("ID Filters")); // Grouping name
    };

    // Use a robust hook to ensure it loads on every refresh/route change
    $(document).on("app_ready", function () {
        frappe.views.ListView.prototype.refresh_header = (function (original) {
            return function () {
                original.apply(this, arguments);
                add_id_filter_group(this);
            };
        })(frappe.views.ListView.prototype.refresh_header);
    });
})();
