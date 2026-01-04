document.addEventListener('DOMContentLoaded', () => {
    const tableBody = document.getElementById('commandTable');
    const searchInput = document.getElementById('searchInput');
    const lastSync = document.getElementById('lastSync');
    const commandCount = document.getElementById('commandCount');

    let commands = [];

    // Helper to format permission badges
    function getPermissionBadge(perm) {
        const p = perm.toLowerCase();
        return `<span class="permission-tag permission-${p}">${perm}</span>`;
    }

    // Render table
    function renderTable(data) {
        tableBody.innerHTML = '';

        if (data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:40px; color:rgba(255,255,255,0.5);">No commands found</td></tr>';
            return;
        }

        data.forEach(cmd => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td style="font-weight:600; color: #667eea;">${cmd.trigger}</td>
                <td>${cmd.response}</td>
                <td>${getPermissionBadge(cmd.permission)}</td>
                <td><span class="type-tag">${cmd.type}</span></td>
            `;
            tableBody.appendChild(row);
        });

        // Update command count
        if (commandCount) {
            commandCount.textContent = data.length;
        }
    }

    // CONFIGURATION:
    // To enable "Realtime Sync" via Gist:
    // 1. Create a Public Gist with a "data.json" file.
    // 2. Get the "Raw" URL (remove the commit hash part to keep it always latest).
    //    Format: https://gist.githubusercontent.com/<user>/<id>/raw/data.json
    // 3. Paste it below.
    const GIST_URL = ""; // TODO: PASTE YOUR RAW GIST URL HERE (See COMMANDS_PAGE_SETUP.md)

    // Fetch data with cache-buster
    const baseUrl = GIST_URL || 'data.json';
    const url = baseUrl + (baseUrl.includes('http') ? ('?t=' + new Date().getTime()) : '');

    fetch(url)
        .then(response => response.json())
        .then(data => {
            // Sort A-Z by trigger
            commands = data.sort((a, b) => a.trigger.localeCompare(b.trigger));
            renderTable(commands);

            if (GIST_URL) {
                const now = new Date();
                const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
                lastSync.innerHTML = `<span style="color:#56ab2f;">●</span> ${time}`;
            } else {
                lastSync.textContent = 'Local File';
            }
        })
        .catch(error => {
            console.warn('CORS restricted or file not found. Using fallback data.');
            // Fallback for local testing
            commands = [
                { trigger: "!sample", response: "This is sample data (configure GIST_URL in app.js)", permission: "everyone", type: "Demo" },
                { trigger: "!discord", response: "Join our community!", permission: "everyone", type: "Custom" }
            ];
            renderTable(commands);
            lastSync.innerHTML = '<span style="color:#ff6b6b;">●</span> Demo Mode';
        });

    // Search filter
    searchInput.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        const filtered = commands.filter(cmd =>
            cmd.trigger.toLowerCase().includes(term) ||
            cmd.response.toLowerCase().includes(term) ||
            cmd.permission.toLowerCase().includes(term) ||
            cmd.type.toLowerCase().includes(term)
        );
        renderTable(filtered);
    });

    // Auto-refresh every 5 minutes if using Gist
    if (GIST_URL) {
        setInterval(() => {
            fetch(url + '&t=' + new Date().getTime())
                .then(response => response.json())
                .then(data => {
                    commands = data.sort((a, b) => a.trigger.localeCompare(b.trigger));
                    const currentSearch = searchInput.value.toLowerCase();
                    if (currentSearch) {
                        const filtered = commands.filter(cmd =>
                            cmd.trigger.toLowerCase().includes(currentSearch) ||
                            cmd.response.toLowerCase().includes(currentSearch) ||
                            cmd.permission.toLowerCase().includes(currentSearch) ||
                            cmd.type.toLowerCase().includes(currentSearch)
                        );
                        renderTable(filtered);
                    } else {
                        renderTable(commands);
                    }
                    const now = new Date();
                    const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
                    lastSync.innerHTML = `<span style="color:#56ab2f;">●</span> ${time}`;
                });
        }, 300000); // 5 minutes
    }
});
