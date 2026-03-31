(function () {
	function add_id_operators() {
		const rows = document.querySelectorAll('[data-fieldname], .filter-row, .filter-field');

		rows.forEach((row) => {
			const selects = row.querySelectorAll('select');
			if (selects.length < 2) return;

			const fieldSelect = selects[0];
			const operatorSelect = selects[1];

			const fieldValue = (fieldSelect.value || "").toLowerCase();
			const fieldText =
				fieldSelect.options[fieldSelect.selectedIndex]?.text?.toLowerCase() || "";

			const isIdField =
				fieldValue === "name" ||
				fieldValue === "id" ||
				fieldText === "id" ||
				fieldText === "name";

			if (!isIdField) return;

			const hasBefore = Array.from(operatorSelect.options).some(
				(opt) => opt.value === "<"
			);
			const hasAfter = Array.from(operatorSelect.options).some(
				(opt) => opt.value === ">"
			);

			if (!hasBefore) {
				const opt = document.createElement("option");
				opt.value = "<";
				opt.text = "Before";
				operatorSelect.appendChild(opt);
			}

			if (!hasAfter) {
				const opt = document.createElement("option");
				opt.value = ">";
				opt.text = "After";
				operatorSelect.appendChild(opt);
			}
		});
	}

	function relabel_existing_options() {
		document.querySelectorAll("select").forEach((select) => {
			Array.from(select.options).forEach((opt) => {
				if (opt.value === "<") opt.text = "Before";
				if (opt.value === ">") opt.text = "After";
			});
		});
	}

	function patch() {
		add_id_operators();
		relabel_existing_options();
	}

	const observer = new MutationObserver(() => {
		patch();
	});

	function start() {
		patch();
		observer.observe(document.body, {
			childList: true,
			subtree: true,
		});

		document.body.addEventListener("click", function () {
			setTimeout(patch, 150);
		});

		document.body.addEventListener("change", function () {
			setTimeout(patch, 150);
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", start);
	} else {
		start();
	}
})();
