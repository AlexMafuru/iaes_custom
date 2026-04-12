frappe.query_reports["Open Opportunities Assigned Summary"] = {
	"filters": [
        // Add your filters here if you have any (e.g., Company, Date Range)
    ],
	"get_chart": function(columns, result) {
		// 1. Initialize counts
		let healthy = 0, attention = 0, critical = 0;

		// 2. Loop through the result rows (excluding the TOTAL row)
		result.forEach(row => {
			if (row.assigned_user !== "<b>TOTAL</b>") {
				if (row.health_indicator.includes("Healthy")) healthy++;
				if (row.health_indicator.includes("Attention")) attention++;
				if (row.health_indicator.includes("Critical")) critical++;
			}
		});

		// 3. Return the chart object
		return {
			data: {
				labels: ["Healthy", "Attention", "Critical"],
				datasets: [
					{
						name: "Team Status",
						values: [healthy, attention, critical]
					}
				]
			},
			type: 'donut', // Donut or 'percentage' works best for health distribution
			height: 250,
			colors: ["#28a745", "#fd7e14", "#dc3545"] // Green, Orange, Red
		};
	}
};