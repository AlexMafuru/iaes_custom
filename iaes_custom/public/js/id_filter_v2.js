(function () {
    // The core function to inject our grouped menu
    const inject_id_filters = (listview) => {
        // Guard clause: ensure page exists and we haven't already added buttons
        if (!listview || !listview.page || listview.page.__id_filters_added) return;
        
        // 1. Add "Before" to the "ID Filters" group
        listview.page.add_inner_button(__("Before"), () => {
            let d = new frappe.ui.Dialog({
                title: __("Filter: ID Before"),
                fields: [{ 
                    label: __("Document ID"), 
                    fieldname: "doc_id", 
                    fieldtype: "Data", 
                    reqd: 1 
                }],
                primary_action_label: __("Apply"),
                primary_action(values) {
                    listview.filter_area.add([[listview.doctype, "name", "<", values.doc_id]]);
                    d.hide();
                }
            });
            d.show();
        }, __("ID Filters"));

        // 2. Add "After" to the same "ID Filters" group
        listview.page.add_inner_button(__("After"), () => {
            let d = new frappe.ui.Dialog({
                title: __("Filter: ID After"),
                fields: [{ 
                    label: __("Document ID"), 
                    fieldname: "doc_id", 
                    fieldtype: "Data", 
                    reqd: 1 
                }],
                primary_action_label: __("Apply"),
                primary_action(values) {
                    listview.filter_area.add([[listview.doctype, "name", ">", values.doc_id]]);
                    d.hide();
                }
            });
            d.show();
        }, __("ID Filters"));

        // Mark as added so we don't duplicate on every refresh
        listview.page.__id_filters_added = true;
    };

    // GLOBAL HOOK: We patch the standard ListView header refresh
    // This ensures that whenever ANY list is loaded or filtered, our buttons are checked
    $(document).on("app_ready", function () {
        if (frappe.views.ListView) {
            const original_refresh = frappe.views.ListView.prototype.refresh_header;
            frappe.views.ListView.prototype.refresh_header = function () {
                original_refresh.apply(this, arguments);
                inject_id_filters(this);
            };
        }
    });
})();
