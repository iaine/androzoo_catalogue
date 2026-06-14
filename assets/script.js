// Wait for pywebview to inject the Python API before wiring up the form.
window.addEventListener('pywebviewready', () => {
    const btn = document.getElementById('search-btn');
    const statusEl = document.getElementById('status');
    const resultEl = document.getElementById('result');
    const errorEl = document.getElementById('error');

    function show(el) { el.hidden = false; }
    function hide(el) { el.hidden = true; }

    btn.addEventListener('click', () => {
        const apk_name = document.getElementById('apk_name').value.trim();
        const store = document.getElementById('store').value.trim();
        const start = document.getElementById('start').value.trim();
        const end = document.getElementById('end').value.trim();

        if (!apk_name && !store && !start && !end) {
            document.getElementById('hint').textContent =
                'Please enter at least one filter before searching.';
            return;
        }

        hide(resultEl);
        hide(errorEl);
        show(statusEl);
        btn.disabled = true;

        window.pywebview.api.search_catalogue(apk_name, store, start, end);
    });
});

// Called from Python (app.py) when the search finishes successfully.
function onSearchDone(info) {
    document.getElementById('search-btn').disabled = false;
    document.getElementById('status').hidden = true;

    document.getElementById('result-count').textContent =
        info.matches + (info.matches === 1 ? ' match' : ' matches');
    document.getElementById('result-path').textContent = info.path;
    document.getElementById('result').hidden = false;
}

// Called from Python (app.py) when the search fails.
function onSearchError(err) {
    document.getElementById('search-btn').disabled = false;
    document.getElementById('status').hidden = true;

    document.getElementById('error-text').textContent =
        err.message || 'Unknown error.';
    document.getElementById('error').hidden = false;
}
