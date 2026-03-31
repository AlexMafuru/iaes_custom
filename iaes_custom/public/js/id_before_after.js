frappe.listview_settings["Purchase Invoice"] = {
    onload(listview) {

        if (listview.page.__iaes_buttons_added) return;
        listview.page.__iaes_buttons_added = true;

        listview.page.add_inner_button("ID Before", function () {

            const d = new frappe.ui.Dialog({
                title: "Filter ID Before",
                fields: [
                    {
                        label: "Purchase Invoice ID",
                        fieldname: "doc_id",
                        fieldtype: "Data",
                        reqd: 1
                    }
                ],
                primary_action_label: "Apply",
                primary_action(values) {

                    listview.filter_area.add([
                        ["Purchase Invoice", "name", "<", values.doc_id]
                    ]);

                    d.hide();
                }
            });

            d.show();
        });


        listview.page.add_inner_button("ID After", function () {

            const d = new frappe.ui.Dialog({
                title: "Filter ID After",
                fields: [
                    {
                        label: "Purchase Invoice ID",
                        fieldname: "doc_id",
                        fieldtype: "Data",
                        reqd: 1
                    }
                ],
                primary_action_label: "Apply",
                primary_action(values) {

                    listview.filter_area.add([
                        ["Purchase Invoice", "name", ">", values.doc_id]
                    ]);

                    d.hide();
                }
            });

            d.show();
        });

    }
};
