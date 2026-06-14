// AndroZoo catalogue search — submit a job, poll until done, then download.

const btn = document.getElementById('search-btn');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const errorEl = document.getElementById('error');
const hint = document.getElementById('hint');

const POLL_INTERVAL_MS = 3000;

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function showError(message) {
    btn.disabled = false;
    hide(statusEl);
    document.getElementById('error-text').textContent = message || 'Unknown error.';
    show(errorEl);
}

async function startSearch() {
    const params = {
        apk_name: document.getElementById('apk_name').value.trim(),
        store: document.getElementById('store').value.trim(),
        start: document.getElementById('start').value.trim(),
        end: document.getElementById('end').value.trim(),
    };

    if (!params.apk_name && !params.store && !params.start && !params.end) {
        hint.textContent = 'Please enter at least one filter before searching.';
        return;
    }

    hide(resultEl);
    hide(errorEl);
    show(statusEl);
    btn.disabled = true;

    try {
        const resp = await fetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showError(data.error);
            return;
        }
        pollStatus(data.job_id);
    } catch (e) {
        showError('Could not reach the server.');
    }
}

function pollStatus(jobId) {
    const tick = async () => {
        try {
            const resp = await fetch(`/search/${jobId}`);
            const data = await resp.json();

            if (data.status === 'running') {
                setTimeout(tick, POLL_INTERVAL_MS);
            } else if (data.status === 'done') {
                btn.disabled = false;
                hide(statusEl);
                const n = data.matches;
                document.getElementById('result-count').textContent =
                    n + (n === 1 ? ' match' : ' matches');
                document.getElementById('download-link').href = data.download_url;
                show(resultEl);
            } else {
                showError(data.error);
            }
        } catch (e) {
            showError('Lost connection while waiting for results.');
        }
    };
    setTimeout(tick, POLL_INTERVAL_MS);
}

btn.addEventListener('click', startSearch);
