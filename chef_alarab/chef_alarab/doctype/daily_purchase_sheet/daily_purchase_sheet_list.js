// Status colours in the list view.
frappe.listview_settings["Daily Purchase Sheet"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			Draft: "red",
			Purchasing: "orange",
			Received: "blue",
			Billed: "green",
			Cancelled: "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
