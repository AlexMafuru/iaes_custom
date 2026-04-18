(function() {
    function addComparisonOptions(selectEl) {
        const options = Array.from(selectEl.options).map(o => o.value);
        if (options.includes(">=")) return;
        
        const notEqIndex = options.indexOf("!=");
        const extras = [">", "<", ">=", "<="];
        
        extras.forEach(op => {
            const opt = new Option(op, op);
            if (notEqIndex !== -1) {
                selectEl.add(opt, notEqIndex + 1);
            } else {
                selectEl.add(opt);
            }
        });
    }

    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (!node.querySelectorAll) return;
                node.querySelectorAll('.filter-field select, .filter-list select').forEach(addComparisonOptions);
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
