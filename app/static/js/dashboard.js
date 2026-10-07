// TAGONESWA Commercial Operations Console - Client Controller
function escapeJsAttr(val) {
    if (!val) return '';
    return String(val).replace(/'/g, "\\'");
}

        // =============================================================
        // RBAC & PERMISSION HELPERS
        // =============================================================
        let currentUser = null;
        const canViewBalances = window.canViewBalances !== undefined ? window.canViewBalances : false;
        function hasPermission(permKey) {
            if (!currentUser) return false;
            if (currentUser.role === 'MASTER_ADMIN') return true;
            return (currentUser.effective_permissions || []).includes(permKey);
        }

        // =============================================================
        // MODAL SCROLL CONTROLLER & INTERACTION HANDLERS
        // =============================================================
        const ALL_MODAL_IDS = [
            'cityMinimumsModal',
            'clearPaymentModal',
            'auditLogsModal',
            'addTruckModal',
            'addDriverModal',
            'addSalesRepModal',
            'userManagementModal'
        ];

        function syncBodyScrollLock() {
            const anyOpen = ALL_MODAL_IDS.some(id => {
                const el = document.getElementById(id);
                return el && !el.classList.contains('hidden');
            });
            if (anyOpen) {
                document.body.classList.add('modal-open');
            } else {
                document.body.classList.remove('modal-open');
            }
        }

        function closeModalById(id) {
            switch (id) {
                case 'cityMinimumsModal': closeCityConfigModal(); break;
                case 'clearPaymentModal': closeClearPaymentModal(); break;
                case 'auditLogsModal': closeAuditLogsModal(); break;
                case 'addTruckModal': closeAddTruckModal(); break;
                case 'addDriverModal': closeAddDriverModal(); break;
                case 'addSalesRepModal': closeAddSalesRepModal(); break;
                case 'userManagementModal': closeUserManagementModal(); break;
                default:
                    const el = document.getElementById(id);
                    if (el) el.classList.add('hidden');
                    syncBodyScrollLock();
            }
        }

        function setupModalInteractions() {
            ALL_MODAL_IDS.forEach(id => {
                const modal = document.getElementById(id);
                if (!modal) return;
                // Click on backdrop outside modal-card closes the modal
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) {
                        closeModalById(id);
                    }
                });
                // Prevent scrolling through the overlay backdrop
                modal.addEventListener('wheel', (e) => {
                    if (e.target === modal) {
                        e.preventDefault();
                    }
                }, { passive: false });
                modal.addEventListener('touchmove', (e) => {
                    if (e.target === modal) {
                        e.preventDefault();
                    }
                }, { passive: false });
            });

            // Escape key closes topmost modal
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    for (const id of ALL_MODAL_IDS) {
                        const el = document.getElementById(id);
                        if (el && !el.classList.contains('hidden')) {
                            closeModalById(id);
                            break;
                        }
                    }
                }
            });
        }

        // =============================================================
        // MODAL 7: USER MANAGEMENT & GRANULAR PERMISSIONS
        // =============================================================
        let loadedUsersData = null;
        let selectedMgmtUsername = null;

        function openUserManagementModal() {
            const modal = document.getElementById('userManagementModal');
            if (!modal) return;
            modal.classList.remove('hidden');
            syncBodyScrollLock();
            loadUsersList();
        }

        function closeUserManagementModal() {
            const modal = document.getElementById('userManagementModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        async function loadUsersList() {
            const tbody = document.getElementById('user-mgmt-tbody');
            const countEl = document.getElementById('user-mgmt-count');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-slate-400">Loading user accounts...</td></tr>';

            try {
                const res = await fetch('/api/v2/admin/users');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                loadedUsersData = data;

                if (countEl) countEl.textContent = `${data.users.length} Accounts`;

                tbody.innerHTML = data.users.map(u => {
                    const overridesCount = (u.custom_granted_permissions.length + u.custom_revoked_permissions.length);
                    const overridesBadge = overridesCount > 0
                        ? `<span class="bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 text-[10px] font-bold px-2 py-0.5 rounded-full border border-indigo-300 dark:border-indigo-500/30">+${u.custom_granted_permissions.length} / -${u.custom_revoked_permissions.length} Overrides</span>`
                        : `<span class="text-slate-400 text-[11px]">Role Default</span>`;

                    const statusBadge = u.is_active
                        ? '<span class="bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 font-bold px-2 py-0.5 rounded-full text-[10px] border border-emerald-200 dark:border-emerald-800">Active</span>'
                        : '<span class="bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 font-bold px-2 py-0.5 rounded-full text-[10px] border border-rose-200 dark:border-rose-800">Suspended</span>';

                    const sessionBadge = u.has_active_session
                        ? `<span class="inline-flex items-center gap-1 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 font-bold px-2 py-0.5 rounded-full text-[10px] border border-emerald-200 dark:border-emerald-800" title="Last login: ${escapeJsAttr(u.last_login_at)} (IP: ${escapeJsAttr(u.last_login_ip)})"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Connected</span>`
                        : `<span class="text-slate-400 text-[10px]">No Device Active</span>`;

                    const companyBadge = u.company ? `<span class="bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-[10px] font-bold px-2 py-0.5 rounded-full border border-blue-200 dark:border-blue-800 ml-1.5">${escapeJsAttr(u.company)}</span>` : '';

                    return `
                        <tr class="hover:bg-slate-50 dark:hover:bg-[#16161e] transition">
                            <td class="px-4 py-2.5">
                                <div class="font-bold text-slate-900 dark:text-zinc-100 flex items-center flex-wrap gap-1">
                                    <span>${u.username}</span>
                                    ${companyBadge}
                                </div>
                                <div class="text-[11px] text-slate-500">${u.full_name || '--'}</div>
                            </td>
                            <td class="px-4 py-2.5">
                                <span class="bg-slate-100 dark:bg-zinc-800 text-slate-800 dark:text-zinc-200 px-2 py-0.5 rounded text-[11px] font-mono font-bold">${u.role}</span>
                            </td>
                            <td class="px-4 py-2.5">${statusBadge}</td>
                            <td class="px-4 py-2.5">${sessionBadge}</td>
                            <td class="px-4 py-2.5">${overridesBadge}</td>
                            <td class="px-4 py-2.5 text-right whitespace-nowrap">
                                <button onclick="selectUserForEdit('${u.username}')" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-2.5 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer">
                                    Manage
                                </button>
                                <button onclick="revokeUserSessions('${u.username}')" class="bg-amber-50 hover:bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:hover:bg-amber-900/60 dark:text-amber-300 font-bold px-2 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer ml-1" title="Force Logout All Devices">
                                    🔒 Disconnect
                                </button>
                                ${u.username !== 'admin' ? `
                                <button onclick="toggleUserActiveStatus('${u.username}', ${!u.is_active})" class="${u.is_active ? 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:text-zinc-300' : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:hover:bg-emerald-900/60 dark:text-emerald-300'} font-bold px-2 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer ml-1" title="${u.is_active ? 'Suspend Account' : 'Reactivate Account'}">
                                    ${u.is_active ? 'Suspend' : 'Activate'}
                                </button>
                                <button onclick="deleteUserAccount('${u.username}')" class="bg-rose-50 hover:bg-rose-100 text-rose-600 dark:bg-rose-950/40 dark:hover:bg-rose-900/60 dark:text-rose-400 font-bold px-2 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer ml-1" title="Delete Account Permanently">
                                    Remove
                                </button>` : ''}
                            </td>
                        </tr>
                    `;
                }).join('');

                if (selectedMgmtUsername) {
                    selectUserForEdit(selectedMgmtUsername);
                }
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-rose-500 font-bold">Failed to load users: ${err.message}</td></tr>`;
            }
        }

        function selectUserForEdit(uname) {
            if (!loadedUsersData || !loadedUsersData.users) return;
            const u = loadedUsersData.users.find(x => x.username.toLowerCase() === uname.toLowerCase());
            if (!u) return;

            selectedMgmtUsername = u.username;
            const panel = document.getElementById('user-mgmt-detail-panel');
            if (panel) panel.classList.remove('hidden');

            const header = document.getElementById('selected-user-header');
            if (header) header.textContent = `${u.username} (${u.full_name || u.role})`;

            const roleSelect = document.getElementById('selected-user-role');
            if (roleSelect) roleSelect.value = u.role;

            const activeCheck = document.getElementById('selected-user-active');
            if (activeCheck) activeCheck.checked = u.is_active;

            const sessInfo = document.getElementById('selected-user-session-info');
            if (sessInfo) {
                sessInfo.innerHTML = `<span>🛡️ <strong>Single Active Session Enforced</strong> | Status: <strong>${u.is_active ? 'Active' : 'Suspended'}</strong> | Device: <strong>${u.has_active_session ? '🟢 Connected' : '⚪ Disconnected'}</strong> (Last: ${escapeJsAttr(u.last_login_at)} IP: ${escapeJsAttr(u.last_login_ip)})</span>`;
            }

            const toggleStatusBtn = document.getElementById('btn-toggle-status-panel');
            if (toggleStatusBtn) {
                if (u.username === 'admin') {
                    toggleStatusBtn.classList.add('hidden');
                } else {
                    toggleStatusBtn.classList.remove('hidden');
                    toggleStatusBtn.innerHTML = u.is_active ? '<span>🚫</span> Suspend Account' : '<span>✅</span> Reactivate Account';
                    toggleStatusBtn.className = u.is_active
                        ? 'bg-slate-700 hover:bg-slate-800 text-white font-bold px-3 py-1.5 rounded-xl text-xs transition cursor-pointer shadow-xs flex items-center gap-1'
                        : 'bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-xl text-xs transition cursor-pointer shadow-xs flex items-center gap-1';
                }
            }

            const deleteBtn = document.getElementById('btn-delete-user-panel');
            if (deleteBtn) {
                if (u.username === 'admin') deleteBtn.classList.add('hidden');
                else deleteBtn.classList.remove('hidden');
            }

            const matrix = document.getElementById('user-perms-matrix');
            if (!matrix) return;

            const allPerms = loadedUsersData.all_permissions || [];
            const inherited = new Set(u.inherited_permissions || []);
            const customGranted = new Set(u.custom_granted_permissions || []);
            const customRevoked = new Set(u.custom_revoked_permissions || []);

            matrix.innerHTML = allPerms.map(p => {
                let statusLabel = '';
                let statusClass = '';
                let isEffective = false;

                if (customGranted.has(p)) {
                    statusLabel = 'Explicitly Granted (Override)';
                    statusClass = 'text-emerald-700 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-500/20 border-emerald-300 dark:border-emerald-500/30';
                    isEffective = true;
                } else if (customRevoked.has(p)) {
                    statusLabel = 'Explicitly Revoked (Override)';
                    statusClass = 'text-rose-700 dark:text-rose-300 bg-rose-100 dark:bg-rose-500/20 border-rose-300 dark:border-rose-500/30';
                    isEffective = false;
                } else if (inherited.has(p)) {
                    statusLabel = 'Inherited from Role';
                    statusClass = 'text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/20 border-blue-300 dark:border-blue-500/30';
                    isEffective = true;
                } else {
                    statusLabel = 'Denied (Role Default)';
                    statusClass = 'text-slate-600 dark:text-zinc-400 bg-slate-100 dark:bg-zinc-800 border-slate-300 dark:border-zinc-700';
                    isEffective = false;
                }

                const btnAction = isEffective
                    ? `<button onclick="toggleUserPermissionSubmit('${u.username}', '${p}', false)" class="bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/30 dark:hover:bg-rose-900/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900/50 font-bold px-2.5 py-1 rounded-lg text-[10px] transition cursor-pointer">Revoke</button>`
                    : `<button onclick="toggleUserPermissionSubmit('${u.username}', '${p}', true)" class="bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:hover:bg-emerald-900/50 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900/50 font-bold px-2.5 py-1 rounded-lg text-[10px] transition cursor-pointer">Grant</button>`;

                return `
                    <div class="bg-white dark:bg-[#181820] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 flex items-center justify-between gap-2 shadow-xs">
                        <div class="overflow-hidden">
                            <div class="text-xs font-mono font-bold text-slate-800 dark:text-zinc-200 truncate">${p}</div>
                            <div class="mt-1 inline-flex items-center text-[9px] font-bold px-2 py-0.5 rounded-full border ${statusClass}">
                                ${statusLabel}
                            </div>
                        </div>
                        <div>
                            ${btnAction}
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function saveSelectedUserRole() {
            if (!selectedMgmtUsername) return;
            const roleSelect = document.getElementById('selected-user-role');
            const activeCheck = document.getElementById('selected-user-active');
            if (!roleSelect || !activeCheck) return;

            const newRole = roleSelect.value;
            const isActive = activeCheck.checked;
            const reason = prompt(`Enter reason for updating role of '${selectedMgmtUsername}' to ${newRole}:`);
            if (!reason || !reason.trim()) {
                alert('A reason is mandatory for user role updates.');
                return;
            }

            try {
                const res = await fetch('/api/v2/admin/users/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: selectedMgmtUsername,
                        role: newRole,
                        is_active: isActive,
                        reason: reason.trim()
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Updated ${selectedMgmtUsername} to ${newRole}!`);
                    await loadUsersList();
                } else {
                    alert(data.detail || 'Failed to update user role.');
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        }

        async function deleteUserAccount(uname) {
            if (uname === 'admin') {
                alert('Cannot delete super administrator admin.');
                return;
            }
            if (!confirm(`Are you sure you want to remove user account '${uname}'?`)) return;
            try {
                const res = await fetch('/api/v2/admin/users/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: uname })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`User account '${uname}' removed.`);
                    if (selectedMgmtUsername === uname) {
                        selectedMgmtUsername = null;
                        const panel = document.getElementById('user-mgmt-detail-panel');
                        if (panel) panel.classList.add('hidden');
                    }
                    await loadUsersList();
                } else {
                    alert(data.detail || 'Failed to remove user account.');
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        }
        window.deleteUserAccount = deleteUserAccount;

        async function revokeUserSessions(uname) {
            if (!confirm(`Force logout all devices and terminate active sessions for '${uname}'?`)) return;
            try {
                const res = await fetch('/api/v2/admin/users/revoke-sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: uname })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || `Active sessions revoked for ${uname}.`);
                    await loadUsersList();
                } else {
                    alert(data.detail || 'Failed to revoke sessions.');
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        }
        window.revokeUserSessions = revokeUserSessions;

        async function toggleUserActiveStatus(uname, newStatus) {
            const actionWord = newStatus ? 'activate' : 'suspend';
            if (!confirm(`Are you sure you want to ${actionWord} the account '${uname}'?`)) return;
            try {
                const res = await fetch('/api/v2/admin/users/toggle-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: uname, is_active: newStatus })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || `User account status updated.`);
                    await loadUsersList();
                } else {
                    alert(data.detail || 'Failed to update account status.');
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        }
        window.toggleUserActiveStatus = toggleUserActiveStatus;

        function toggleSelectedUserStatus() {
            if (!selectedMgmtUsername || !loadedUsersData || !loadedUsersData.users) return;
            const u = loadedUsersData.users.find(x => x.username.toLowerCase() === selectedMgmtUsername.toLowerCase());
            if (!u) return;
            toggleUserActiveStatus(u.username, !u.is_active);
        }
        window.toggleSelectedUserStatus = toggleSelectedUserStatus;

        function openCreateUserModal() {
            const m = document.getElementById('createUserModal');
            if (m) {
                m.classList.remove('hidden');
                const uInput = document.getElementById('create-user-username');
                if (uInput) {
                    uInput.value = '';
                    uInput.focus();
                }
                const pInput = document.getElementById('create-user-password');
                if (pInput) pInput.value = '';
                const fInput = document.getElementById('create-user-fullname');
                if (fInput) fInput.value = '';
                const cInput = document.getElementById('create-user-company');
                if (cInput) cInput.value = '';
                const phInput = document.getElementById('create-user-phone');
                if (phInput) phInput.value = '';
            }
        }
        window.openCreateUserModal = openCreateUserModal;

        function closeCreateUserModal() {
            const m = document.getElementById('createUserModal');
            if (m) m.classList.add('hidden');
        }
        window.closeCreateUserModal = closeCreateUserModal;

        async function submitCreateUser() {
            const uname = (document.getElementById('create-user-username')?.value || '').trim();
            const pass = (document.getElementById('create-user-password')?.value || '').trim();
            const fname = (document.getElementById('create-user-fullname')?.value || '').trim();
            const role = document.getElementById('create-user-role')?.value || 'SALES_ADMIN';
            const company = (document.getElementById('create-user-company')?.value || '').trim();
            const phone = (document.getElementById('create-user-phone')?.value || '').trim();

            if (!uname || uname.length < 3) {
                alert('Username must be at least 3 characters.');
                return;
            }
            if (!pass || pass.length < 6) {
                alert('Password must be at least 6 characters.');
                return;
            }

            try {
                const res = await fetch('/api/v2/admin/users/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: uname,
                        password: pass,
                        full_name: fname,
                        role: role,
                        company: company,
                        phone: phone
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Created account '${data.username}'!`);
                    closeCreateUserModal();
                    await loadUsersList();
                } else {
                    alert(data.detail || 'Failed to create user account.');
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        }
        window.submitCreateUser = submitCreateUser;

        async function toggleUserPermissionSubmit(username, permissionKey, isGranted) {
            const actionWord = isGranted ? 'grant' : 'revoke';
            const reason = prompt(`Reason to ${actionWord} '${permissionKey}' for ${username}:`);
            if (!reason || !reason.trim()) {
                alert('A reason is mandatory for permission overrides.');
                return;
            }

            try {
                const res = await fetch('/api/v2/admin/users/permissions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: username,
                        permission_key: permissionKey,
                        is_granted: isGranted,
                        reason: reason.trim()
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Permission ${permissionKey} ${actionWord}ed for ${username}!`);
                    await loadUsersList();
                } else {
                    alert(data.detail || `Failed to ${actionWord} permission.`);
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        }

        let cachedData = null;
        let isRefreshing = false;
        const initialAllowedDomains = window.initialAllowedDomains || [];
        const initialDefaultTab = window.initialDefaultTab || 'logistics';
        // Pagination state
        let itPage = 1, itPageSize = 15;
        let projPage = 1, projPageSize = 15;
        let wsPage = 1, wsPageSize = 15;
        let fleetPage = 1, fleetPageSize = 15;
        let ledgerPage = 1, ledgerPageSize = 15;
        let tripsPage = 1, tripsPageSize = 15;
        let trucksPage = 1, trucksPageSize = 15;
        let driversPage = 1, driversPageSize = 15;
        let paymentsPage = 1, paymentsPageSize = 15;

        function renderPaginationControls(infoId, controlsId, currentPage, totalCount, pageSize, changeFnName) {
            const infoEl = document.getElementById(infoId);
            const controlsEl = document.getElementById(controlsId);
            if (!infoEl || !controlsEl) return;

            if (totalCount === 0) {
                infoEl.textContent = 'Showing 0 of 0 entries';
                controlsEl.innerHTML = '';
                return;
            }

            const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
            const startItem = (currentPage - 1) * pageSize + 1;
            const endItem = Math.min(currentPage * pageSize, totalCount);

            infoEl.innerHTML = `Showing <strong class="text-slate-900 dark:text-zinc-100">${startItem}–${endItem}</strong> of <strong class="text-slate-900 dark:text-zinc-100">${totalCount}</strong> entries`;

            if (totalPages <= 1) {
                controlsEl.innerHTML = '';
                return;
            }

            const isPrevDisabled = currentPage <= 1;
            const isNextDisabled = currentPage >= totalPages;

            const btnClass = "px-2.5 py-1 text-xs rounded-lg font-bold border transition cursor-pointer flex items-center gap-1 ";
            const activeBtnClass = btnClass + "bg-white dark:bg-[#16161c] text-slate-700 dark:text-zinc-200 border-slate-300 dark:border-zinc-700 hover:bg-slate-100 dark:hover:bg-[#202028]";
            const disabledBtnClass = btnClass + "bg-slate-100 dark:bg-[#0f0f13] text-slate-400 dark:text-zinc-600 border-slate-200 dark:border-zinc-800 cursor-not-allowed opacity-50";

            controlsEl.innerHTML = `
                <button onclick="${changeFnName}(${currentPage - 1})" ${isPrevDisabled ? 'disabled' : ''} class="${isPrevDisabled ? disabledBtnClass : activeBtnClass}">
                    ‹ Prev
                </button>
                <span class="text-xs font-semibold px-2 text-slate-600 dark:text-zinc-400">
                    Page <strong class="text-slate-900 dark:text-zinc-100 font-mono">${currentPage}</strong> of <strong class="text-slate-900 dark:text-zinc-100 font-mono">${totalPages}</strong>
                </span>
                <button onclick="${changeFnName}(${currentPage + 1})" ${isNextDisabled ? 'disabled' : ''} class="${isNextDisabled ? disabledBtnClass : activeBtnClass}">
                    Next ›
                </button>
            `;
        }

        function changeITPage(p) { itPage = p; filterITTable(false); }
        function changeProjPage(p) { projPage = p; filterProjectsTable(false); }
        function changeWSPage(p) { wsPage = p; filterFleetTable(false); }
        function changeFleetPage(p) { fleetPage = p; filterFleetApprovalsTable(false); }
        function changeLedgerPage(p) { ledgerPage = p; filterLedgerTable(false); }
        function changeTripsPage(p) { tripsPage = p; filterTripsTable(false); }
        function changeTrucksPage(p) { trucksPage = p; filterTrucksTable(false); }
        function changeDriversPage(p) { driversPage = p; filterDriversTable(false); }
        function changePaymentsPage(p) { paymentsPage = p; filterPaymentsTable(false); }

        // -------------------------------------------------------------
        // Sliding Sidebar Controller
        // -------------------------------------------------------------
        function toggleSidebar(open) {
            const sidebar = document.getElementById('sliding-sidebar');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (!sidebar || !backdrop) return;
            if (open) {
                sidebar.classList.remove('-translate-x-full');
                backdrop.classList.remove('hidden');
            } else {
                sidebar.classList.add('-translate-x-full');
                backdrop.classList.add('hidden');
            }
        }

        // -------------------------------------------------------------
        // Fleet Operations Sub-View Switcher
        // -------------------------------------------------------------
        let currentFleetSubView = 'overview';
        function switchFleetSubView(viewId) {
            if (!canViewBalances && !hasPermission('manage_sales_pipeline') && viewId === 'salespersons') {
                viewId = 'overview';
            }
            if (!canViewBalances && (viewId === 'payments' || viewId === 'ledger')) {
                viewId = 'overview';
            }
            if (window.currentUserRole !== 'MASTER_ADMIN' && viewId === 'analytics') {
                viewId = 'overview';
            }
            currentFleetSubView = viewId;
            const sel = document.getElementById('fleet-view-selector');
            if (sel && sel.value !== viewId) sel.value = viewId;

            document.querySelectorAll('.fleet-quick-pill').forEach(btn => {
                if (btn.getAttribute('data-view') === viewId) {
                    btn.classList.add('bg-blue-600', 'text-white', 'shadow-xs');
                    btn.classList.remove('text-slate-600', 'dark:text-zinc-300', 'hover:bg-slate-100', 'dark:hover:bg-zinc-800');
                } else {
                    btn.classList.remove('bg-blue-600', 'text-white', 'shadow-xs');
                    btn.classList.add('text-slate-600', 'dark:text-zinc-300', 'hover:bg-slate-100', 'dark:hover:bg-zinc-800');
                }
            });

            document.querySelectorAll('.fleet-subview-btn').forEach(btn => {
                btn.classList.remove('bg-blue-600', 'text-white', 'shadow-md');
                btn.classList.add('bg-white', 'dark:bg-[#121216]', 'text-slate-700', 'dark:text-zinc-300');
            });
            const activeBtn = document.getElementById('fleet-btn-' + viewId);
            if (activeBtn) {
                activeBtn.classList.add('bg-blue-600', 'text-white', 'shadow-md');
                activeBtn.classList.remove('bg-white', 'dark:bg-[#121216]', 'text-slate-700', 'dark:text-zinc-300');
            }

            const subviews = ['overview', 'trips', 'salespersons', 'payments', 'trucks', 'drivers', 'approvals', 'ledger', 'analytics'];
            subviews.forEach(sv => {
                const el = document.getElementById('fleet-section-' + sv);
                if (el) {
                    if (sv === 'analytics' && window.currentUserRole !== 'MASTER_ADMIN') {
                        el.style.display = 'none';
                    } else if (viewId === 'all' || viewId === sv) {
                        el.style.display = 'block';
                    } else {
                        el.style.display = 'none';
                    }
                }
            });

            if (window.currentUserRole === 'MASTER_ADMIN' && (viewId === 'analytics' || viewId === 'all') && window.lastFleetAnalytics) {
                requestAnimationFrame(() => {
                    setTimeout(() => {
                        renderAnalyticsSection(window.lastFleetAnalytics, window.lastFleetStats);
                    }, 80);
                });
            }
        }

        window.selectedFleetCompany = 'ALL';
        window.currentSalespersonCompanyFilter = 'ALL';

        function switchFleetCompany(comp) {
            window.selectedFleetCompany = comp;
            window.currentSalespersonCompanyFilter = comp;

            // Update company division pills UI
            document.querySelectorAll('.fleet-company-pill').forEach(btn => {
                btn.classList.remove('bg-blue-600', 'text-white', 'shadow-xs');
                btn.classList.add('text-slate-600', 'dark:text-zinc-300', 'hover:bg-slate-100', 'dark:hover:bg-zinc-800');
            });
            const pillId = comp === 'ALL' ? 'fleet-comp-ALL' :
                           comp.includes('LG') ? 'fleet-comp-LG' :
                           comp.includes('Tagoneswa') ? 'fleet-comp-TG' : 'fleet-comp-Kreckle';
            const activePill = document.getElementById(pillId);
            if (activePill) {
                activePill.classList.add('bg-blue-600', 'text-white', 'shadow-xs');
                activePill.classList.remove('text-slate-600', 'dark:text-zinc-300', 'hover:bg-slate-100', 'dark:hover:bg-zinc-800');
            }

            // Synchronize subview salesperson buttons
            filterSalespersonsByCompany(comp);

            // Re-filter Trips table
            if (typeof filterTripsTable === 'function') filterTripsTable(true);

            // Re-filter Approvals table
            if (typeof filterFleetApprovalsTable === 'function') filterFleetApprovalsTable(true);
            if (typeof filterApprovalsTable === 'function') filterApprovalsTable(true);

            // Re-render Analytics & KPIs for this company
            updateCompanyPartitionedKPIs();
        }

        function updateCompanyPartitionedKPIs() {
            if (!cachedData || !cachedData.fleet) return;
            const fleet = cachedData.fleet;
            const comp = window.selectedFleetCompany || 'ALL';

            if (comp === 'ALL') {
                // Master / overall data across all 3 companies
                const tripsEl = document.getElementById('fleet-stat-trips');
                if (tripsEl && fleet.stats) tripsEl.textContent = fleet.stats.total_trips ?? 0;

                const approvedEl = document.getElementById('fleet-stat-approved');
                if (approvedEl && fleet.stats) approvedEl.textContent = fleet.stats.approved_trips ?? 0;

                const shortfallsEl = document.getElementById('fleet-stat-shortfalls');
                if (shortfallsEl && fleet.stats) shortfallsEl.textContent = fleet.stats.shortfall_trips ?? 0;

                const transportEl = document.getElementById('fleet-stat-transport');
                if (transportEl && fleet.stats) transportEl.textContent = '$' + Number(fleet.stats.total_transport_charges || 0).toFixed(2);

                const backlogEl = document.getElementById('fleet-stat-backlog');
                if (backlogEl && fleet.stats) backlogEl.textContent = '$' + Number(fleet.stats.total_outstanding_backlog || 0).toFixed(2);

                const masterApp = document.getElementById('master-active-ops');
                if (masterApp && fleet.overview?.kpis) masterApp.textContent = fleet.overview.kpis.pending_trip_approvals ?? 0;

                if (window.lastFleetAnalytics && window.lastFleetStats) {
                    renderAnalyticsSection(window.lastFleetAnalytics, window.lastFleetStats);
                }
            } else {
                // Company-specific partitioned data
                const cLower = comp.toLowerCase();
                const trips = (fleet.trips || []).filter(t => {
                    const c = (t.company_name || '').toLowerCase();
                    if (cLower.includes('lg')) return c.includes('lg');
                    if (cLower.includes('tagoneswa') || cLower.includes('tg')) return c.includes('tagoneswa') || c.includes('tg') || c.includes('hardware');
                    if (cLower.includes('kreckle')) return c.includes('kreckle');
                    return false;
                });

                const reps = (fleet.salespersons || []).filter(s => {
                    const c = (s.company || '').toLowerCase();
                    if (cLower.includes('lg')) return c.includes('lg');
                    if (cLower.includes('tagoneswa') || cLower.includes('tg')) return c.includes('tagoneswa') || c.includes('tg') || c.includes('hardware');
                    if (cLower.includes('kreckle')) return c.includes('kreckle');
                    return false;
                });

                const totalTrips = trips.length;
                const approvedTrips = trips.filter(t => (t.status || '').toUpperCase().includes('APPROVED') || (t.status || '').toUpperCase().includes('SETTLED') || (t.status || '').toUpperCase().includes('CLOSED')).length;
                const shortfallTrips = trips.filter(t => (t.shortfall || 0) > 0).length;
                const totalTransport = trips.reduce((acc, t) => acc + (t.transport_charge || 0), 0);
                const totalBacklog = reps.reduce((acc, s) => acc + Math.max(0, s.net_balance || 0), 0);

                const tripsEl = document.getElementById('fleet-stat-trips');
                if (tripsEl) tripsEl.textContent = totalTrips;

                const approvedEl = document.getElementById('fleet-stat-approved');
                if (approvedEl) approvedEl.textContent = approvedTrips;

                const shortfallsEl = document.getElementById('fleet-stat-shortfalls');
                if (shortfallsEl) shortfallsEl.textContent = shortfallTrips;

                const transportEl = document.getElementById('fleet-stat-transport');
                if (transportEl) transportEl.textContent = '$' + totalTransport.toFixed(2);

                const backlogEl = document.getElementById('fleet-stat-backlog');
                if (backlogEl) backlogEl.textContent = '$' + totalBacklog.toFixed(2);

                const masterApp = document.getElementById('master-active-ops');
                if (masterApp) masterApp.textContent = trips.filter(t => (t.status || '').toUpperCase().includes('SHORTFALL') || (t.status || '').toUpperCase().includes('QUOTED')).length;

                if (window.lastFleetAnalytics && window.lastFleetStats) {
                    renderAnalyticsSection(window.lastFleetAnalytics, window.lastFleetStats);
                }
            }
        }

        function filterSalespersonsByCompany(comp) {
            window.currentSalespersonCompanyFilter = comp;
            document.querySelectorAll('.sp-filter-btn').forEach(btn => {
                btn.classList.remove('bg-blue-600', 'text-white', 'shadow-xs');
                btn.classList.add('text-slate-600', 'dark:text-zinc-300', 'hover:bg-slate-100', 'dark:hover:bg-zinc-800');
            });
            const btnId = comp === 'ALL' ? 'sp-filter-ALL' :
                          comp.includes('LG') ? 'sp-filter-LG' :
                          comp.includes('Tagoneswa') ? 'sp-filter-TG' : 'sp-filter-Kreckle';
            const activeBtn = document.getElementById(btnId);
            if (activeBtn) {
                activeBtn.classList.add('bg-blue-600', 'text-white', 'shadow-xs');
                activeBtn.classList.remove('text-slate-600', 'dark:text-zinc-300', 'hover:bg-slate-100', 'dark:hover:bg-zinc-800');
            }
            applySalespersonsFilter();
        }

        function filterSalespersonsSearch() {
            applySalespersonsFilter();
        }

        function applySalespersonsFilter() {
            const comp = window.currentSalespersonCompanyFilter || 'ALL';
            const query = (document.getElementById('sp-search-input')?.value || '').toLowerCase().trim();
            const cards = document.querySelectorAll('.salesperson-card');
            cards.forEach(card => {
                const cardComp = card.getAttribute('data-company') || '';
                const cardSearch = card.getAttribute('data-search') || '';
                const matchComp = (comp === 'ALL') ||
                                  cardComp.toLowerCase().includes(comp.toLowerCase()) ||
                                  (comp.includes('Tagoneswa') && cardComp.toLowerCase().includes('tagoneswa')) ||
                                  (comp.includes('LG') && cardComp.toLowerCase().includes('lg')) ||
                                  (comp.includes('Kreckle') && cardComp.toLowerCase().includes('kreckle'));
                const matchQuery = !query || cardSearch.includes(query);
                card.style.display = (matchComp && matchQuery) ? 'flex' : 'none';
            });
        }

        function renderOperationsOverview(overview, user) {
            if (!overview) return;
            const kpis = overview.kpis || {};
            const an = overview.analytics || {};

            // ── TIER 1: ACTION REQUIRED ──────────────────────────────────
            const elPendingApp = document.getElementById('ov-kpi-pending-approvals');
            if (elPendingApp) elPendingApp.textContent = kpis.pending_trip_approvals ?? 0;

            const elShortfallSub = document.getElementById('ov-kpi-shortfall-sub');
            if (elShortfallSub) elShortfallSub.textContent = `${kpis.pending_approvals_shortfall ?? 0} shortfalls, ${kpis.pending_quotes_count ?? 0} quotes`;

            const elBottlenecks = document.getElementById('ov-kpi-bottlenecks');
            if (elBottlenecks) elBottlenecks.textContent = kpis.pending_bottlenecks_count ?? 0;

            // Role-gated Card 5
            const slot5Title = document.getElementById('ov-kpi-slot5-title');
            const slot5Icon  = document.getElementById('ov-kpi-slot5-icon');
            const slot5Val   = document.getElementById('ov-kpi-slot5-val');
            const slot5Sub   = document.getElementById('ov-kpi-slot5-sub');

            if (kpis.sales_pipeline && slot5Title && slot5Val) {
                slot5Title.textContent = 'Sales Pipeline';
                if (slot5Icon) slot5Icon.textContent = 'PIPELINE';
                slot5Val.className = 'text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1 font-mono truncate';
                slot5Val.textContent = '$' + Number(kpis.sales_pipeline.total_invoiced_value || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                if (slot5Sub) slot5Sub.textContent = `${kpis.sales_pipeline.orders_count || 0} orders (${kpis.sales_pipeline.completed_deliveries || 0} delivered)`;
            } else if (kpis.sales_rep_balance && slot5Title && slot5Val) {
                slot5Title.textContent = 'Sales Rep Debt';
                if (slot5Icon) slot5Icon.textContent = 'DEBT';
                const debt = Number(kpis.sales_rep_balance.total_outstanding_debt || 0);
                slot5Val.className = `text-2xl sm:text-3xl font-extrabold mt-1 font-mono truncate ${debt > 0 ? 'text-rose-500 dark:text-rose-400' : 'text-emerald-500 dark:text-emerald-400'}`;
                slot5Val.textContent = '$' + debt.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                if (slot5Sub) slot5Sub.textContent = `${kpis.sales_rep_balance.reps_in_debt || 0} in debt (${kpis.sales_rep_balance.high_alert_count || 0} high alert)`;
            } else if (slot5Title && slot5Val) {
                slot5Title.textContent = 'Fleet Available';
                if (slot5Icon) slot5Icon.textContent = 'FLEET';
                slot5Val.className = 'text-2xl sm:text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-1 font-mono truncate';
                slot5Val.textContent = `${kpis.trucks_available ?? 0}/${kpis.trucks_total ?? 0}`;
                if (slot5Sub) slot5Sub.textContent = 'Commercial vehicles field-ready';
            }

            // Alerts badge
            const alertsBadge = document.getElementById('ov-alerts-count-badge');
            if (alertsBadge) {
                const count = (overview.alerts || []).length;
                alertsBadge.textContent = `${count} active`;
                alertsBadge.className = count > 0
                    ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-amber-200 dark:border-amber-500/30'
                    : 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-500/30';
            }

            // Alerts list
            const alertsList = document.getElementById('ov-alerts-list');
            if (alertsList) {
                if (!overview.alerts || overview.alerts.length === 0) {
                    alertsList.innerHTML = `
                        <div class="py-8 text-center">
                            <div class="text-sm font-extrabold text-slate-800 dark:text-zinc-200">All Operations Clear</div>
                            <p class="text-xs text-slate-500 dark:text-zinc-400 mt-1 max-w-sm mx-auto">No pending exceptions, dispatch bottlenecks, or high-risk balances requiring attention.</p>
                        </div>
                    `;
                } else {
                    alertsList.innerHTML = overview.alerts.map(a => {
                        let sevBorder = 'border-amber-200 dark:border-amber-500/30 bg-amber-500/5';
                        let sevBadge  = 'bg-amber-500/10 text-amber-800 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        if (a.severity === 'urgent') {
                            sevBorder = 'border-rose-200 dark:border-rose-500/30 bg-rose-500/5';
                            sevBadge  = 'bg-rose-500/10 text-rose-800 dark:text-rose-300 border-rose-200 dark:border-rose-500/30 font-bold';
                        } else if (a.severity === 'info') {
                            sevBorder = 'border-blue-200 dark:border-blue-500/30 bg-blue-500/5';
                            sevBadge  = 'bg-blue-500/10 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        }
                        let actionBtnHtml = '';
                        if (a.can_action && !overview.is_read_only) {
                            if (a.modal_target === 'clearPaymentModal') {
                                actionBtnHtml = `<button onclick="openClearPaymentModal()" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-xs whitespace-nowrap cursor-pointer shrink-0">${a.action_label} →</button>`;
                            } else if (a.target_subview) {
                                actionBtnHtml = `<button onclick="switchFleetSubView('${a.target_subview}')" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 dark:bg-zinc-100 hover:bg-slate-800 dark:hover:bg-zinc-200 text-white dark:text-slate-900 transition shadow-xs whitespace-nowrap cursor-pointer shrink-0">${a.action_label} →</button>`;
                            }
                        } else if (overview.is_read_only) {
                            actionBtnHtml = `<span class="text-[10px] text-slate-400 dark:text-zinc-500 font-semibold px-2 py-1 bg-slate-100 dark:bg-[#121216] rounded-lg border border-slate-200 dark:border-zinc-800 whitespace-nowrap">Read-Only</span>`;
                        }
                        return `
                            <div class="pt-3 first:pt-0">
                                <div class="p-3.5 sm:p-4 rounded-xl border ${sevBorder} flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 hover:shadow-xs transition">
                                    <div class="flex items-start gap-3">
                                        <div>
                                            <div class="flex items-center gap-2 flex-wrap">
                                                <span class="text-xs sm:text-sm font-extrabold text-slate-900 dark:text-zinc-100">${a.title}</span>
                                                <span class="text-[10px] px-2 py-0.5 rounded-full border ${sevBadge} font-mono">${a.category}</span>
                                            </div>
                                            <p class="text-xs text-slate-600 dark:text-zinc-400 mt-1 leading-relaxed">${a.description}</p>
                                        </div>
                                    </div>
                                    <div class="self-end sm:self-center">${actionBtnHtml}</div>
                                </div>
                            </div>
                        `;
                    }).join('');
                }
            }

            // ── TIER 2: TODAY'S OPERATIONS ────────────────────────────────
            const elActiveTrips = document.getElementById('ov-kpi-active-trips');
            if (elActiveTrips) elActiveTrips.textContent = kpis.active_ongoing_trips ?? 0;

            const elTransit = document.getElementById('ov-kpi-transit-trips');
            if (elTransit) elTransit.textContent = `${kpis.in_transit_trips ?? 0} in transit`;

            const elDriversActive = document.getElementById('ov-kpi-drivers-active');
            if (elDriversActive) elDriversActive.textContent = kpis.drivers_active ?? 0;

            const elDriversTotal = document.getElementById('ov-kpi-drivers-total');
            if (elDriversTotal) elDriversTotal.textContent = `of ${kpis.drivers_total ?? 0} on roster`;

            const elCompletedTrips = document.getElementById('ov-kpi-completed-trips');
            if (elCompletedTrips) elCompletedTrips.textContent = an.trips_completed ?? 0;

            const elAvgRev = document.getElementById('ov-kpi-avg-revenue');
            if (elAvgRev) elAvgRev.textContent = '100% Verified';

            // ── TIER 3: FLEET STATUS ──────────────────────────────────────
            const elTrucksReady = document.getElementById('ov-kpi-trucks-ready');
            if (elTrucksReady) elTrucksReady.textContent = kpis.trucks_available ?? 0;

            const elInWorkshop = document.getElementById('ov-kpi-trucks-in-workshop');
            if (elInWorkshop) elInWorkshop.textContent = kpis.trucks_in_workshop ?? 0;

            const elAwaitingParts = document.getElementById('ov-kpi-trucks-awaiting-parts');
            if (elAwaitingParts) elAwaitingParts.textContent = kpis.trucks_awaiting_parts ?? 0;

            const elAwaitingQC = document.getElementById('ov-kpi-trucks-awaiting-qc');
            if (elAwaitingQC) elAwaitingQC.textContent = kpis.trucks_awaiting_qc ?? 0;

            const elTrucksTotal = document.getElementById('ov-kpi-trucks-total');
            if (elTrucksTotal) elTrucksTotal.textContent = kpis.trucks_total ?? 0;

            // ── TIER 4: FINANCIAL OVERVIEW ─────────────────────────────────
            const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            setTxt('ov-fin-criteria-status', '100% Verified');
            setTxt('ov-fin-transport-charges', '$' + (an.total_transport_charges || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-fin-total-opex', '$' + (an.total_operational_expenses || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-fin-net-margin', '$' + (an.net_amount || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-fin-debt-backlog', '$' + (an.outstanding_debt_total || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-fin-cleared-payments', '$' + (an.cleared_payments_total || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));

            // ── TIER 5: OPERATIONAL EXPENSES ──────────────────────────────
            setTxt('ov-exp-total-allowances', '$' + (an.total_allowances || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-meals', '$' + (an.total_meals || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-accommodation', '$' + (an.total_accommodation || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-tolls', '$' + (an.total_tolls || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            const totalEmerg = (an.total_emergency_fuel || 0) + (an.total_emergency_other || 0);
            setTxt('ov-exp-total-emergency', '$' + totalEmerg.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-emergency-fuel', '$' + (an.total_emergency_fuel || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-emergency-other', '$' + (an.total_emergency_other || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-avg-opex', '$' + (an.avg_opex_per_trip || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-exp-avg-allowance', '$' + (an.avg_allowance_per_trip || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));

            // ── TIER 6: SALES & REVENUE ANALYSIS ──────────────────────────
            setTxt('ov-rev-recovery-rate', (an.recovery_rate_pct ?? 100) + '%');
            setTxt('ov-rev-shortfall-total', '$' + (an.shortfall_total || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
            setTxt('ov-rev-recovered-total', '$' + (an.recovery_total || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));

            const finSection = document.getElementById('ov-financial-section');
            const finBody    = document.getElementById('ov-financial-body');
            if (finSection && finBody) {
                const bal = kpis.sales_rep_balance;
                const pip = kpis.sales_pipeline;
                if (!bal && !pip) {
                    finSection.style.display = 'none';
                } else {
                    finSection.style.display = '';
                    let rows = '';
                    if (bal) {
                        const debt = Number(bal.total_outstanding_debt || 0);
                        const debtColor = debt > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400';
                        rows += `
                            <div class="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-zinc-800/60 last:border-0">
                                <span class="text-slate-600 dark:text-zinc-400 font-medium">Outstanding Rep Debt</span>
                                <span class="font-extrabold font-mono ${debtColor}">$${debt.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}</span>
                            </div>
                            <div class="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-zinc-800/60 last:border-0">
                                <span class="text-slate-600 dark:text-zinc-400 font-medium">Reps in Debt</span>
                                <span class="font-bold text-slate-800 dark:text-zinc-200">${bal.reps_in_debt ?? 0}</span>
                            </div>
                            <div class="flex items-center justify-between py-1.5 last:border-0">
                                <span class="text-slate-600 dark:text-zinc-400 font-medium">High Alert</span>
                                <span class="font-bold ${(bal.reps_high_alert||0) > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-500 dark:text-zinc-500'}">${bal.reps_high_alert ?? 0} rep(s)</span>
                            </div>
                        `;
                    }
                    if (pip) {
                        rows += `
                            <div class="flex items-center justify-between py-1.5 border-t border-slate-100 dark:border-zinc-800/60">
                                <span class="text-slate-600 dark:text-zinc-400 font-medium">Schedule Variances</span>
                                <span class="font-bold ${(pip.variance_collection||0) > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-zinc-500'}">${pip.variance_collection ?? 0}</span>
                            </div>
                        `;
                    }
                    finBody.innerHTML = rows || '<div class="text-xs text-slate-400 dark:text-zinc-500 text-center py-2">No financial exceptions.</div>';
                }
            }

            // ── TIER 7: ROUTE / CITY PERFORMANCE ──────────────────────────
            const topCitiesBody = document.getElementById('ov-top-cities-body');
            if (topCitiesBody) {
                const cities = an.cities || [];
                if (cities.length === 0) {
                    topCitiesBody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-slate-400 text-xs">No city delivery records found.</td></tr>';
                } else {
                    topCitiesBody.innerHTML = cities.slice(0, 6).map(c => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#14141c] transition">
                            <td class="px-4 py-2 font-bold text-slate-900 dark:text-zinc-100 capitalize">${c.city}</td>
                            <td class="px-4 py-2 text-center font-mono text-slate-700 dark:text-zinc-300">${c.trips}</td>
                            <td class="px-4 py-2 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">✅ Qualified</td>
                            <td class="px-4 py-2 text-right font-mono text-slate-600 dark:text-zinc-300">$${(c.opex || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                        </tr>
                    `).join('');
                }
            }

            // ── TIER 8: FLEET & WORKSHOP PERFORMANCE ─────────────────────
            const utilPct = an.fleet_utilization_pct ?? 0;
            setTxt('ov-perf-utilization', utilPct + '%');
            const utilBar = document.getElementById('ov-perf-util-bar');
            if (utilBar) utilBar.style.width = Math.min(100, Math.max(0, utilPct)) + '%';
            setTxt('ov-perf-ws-impact', (an.workshop_impact_count ?? 0) + ' trucks');

            // ── TIER 9: RECENT OPERATIONS ACTIVITY ────────────────────────
            const actList = document.getElementById('ov-activity-list');
            if (actList) {
                if (!overview.recent_activity || overview.recent_activity.length === 0) {
                    actList.innerHTML = `<div class="p-6 text-center text-slate-400 dark:text-zinc-500 text-xs">No recent operational activities logged.</div>`;
                } else {
                    actList.innerHTML = overview.recent_activity.slice(0, 10).map(act => `
                        <div class="p-3 bg-slate-50 dark:bg-[#121216] border border-slate-200/80 dark:border-zinc-800/80 rounded-xl hover:border-slate-300 dark:hover:border-zinc-700 transition">
                            <div class="flex items-center justify-between gap-2 mb-1">
                                <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${act.badge_class} font-mono uppercase tracking-wider">${act.category}</span>
                                <span class="text-[10px] text-slate-400 dark:text-zinc-500 font-mono">${act.timestamp}</span>
                            </div>
                            <div class="text-xs font-bold text-slate-900 dark:text-zinc-100">${act.title}</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 line-clamp-2">${act.description}</div>
                            <div class="mt-1.5 pt-1 border-t border-slate-200/60 dark:border-zinc-800/60 text-[10px] text-slate-400 dark:text-zinc-500">
                                Actor: <strong class="text-slate-700 dark:text-zinc-300 font-medium">${act.actor}</strong>
                            </div>
                        </div>
                    `).join('');
                }
            }

            // ── TIER 10: RECENT FINANCIAL AUDIT TRAIL ──────────────────────
            const auditBody = document.getElementById('ov-recent-audit-body');
            if (auditBody) {
                const audits = overview.audit_logs || [];
                if (audits.length === 0) {
                    auditBody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-slate-400 text-xs">No financial audit records recorded.</td></tr>';
                } else {
                    auditBody.innerHTML = audits.slice(0, 8).map(al => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#14141c] transition">
                            <td class="px-4 py-2 font-mono text-[11px] text-slate-500 whitespace-nowrap">${al.timestamp}</td>
                            <td class="px-4 py-2 font-bold text-slate-800 dark:text-zinc-200 whitespace-nowrap">${al.username}</td>
                            <td class="px-4 py-2 whitespace-nowrap">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30">
                                    ${(al.action || '').replace(/_/g, ' ')}
                                </span>
                            </td>
                            <td class="px-4 py-2 text-slate-600 dark:text-zinc-300 truncate max-w-xs" title="${al.remarks || al.module}">
                                ${al.remarks || `${al.module} (${al.entity_id || ''})`}
                            </td>
                        </tr>
                    `).join('');
                }
            }
        }

        // =============================================================
        // SUBVIEW 8: DATA ANALYTICS RENDERER (CHART.JS INTEGRATED)
        // =============================================================
        window.analyticsCharts = window.analyticsCharts || {};
        window.lastFleetAnalytics = null;
        window.lastFleetStats = null;
        window.currentSalesChartMode = 'DAY';

        function destroyAnalyticsChart(key) {
            if (window.analyticsCharts[key]) {
                try { window.analyticsCharts[key].destroy(); } catch (e) { /* ignore */ }
                delete window.analyticsCharts[key];
            }
        }

        function switchSalesChartMode(mode) {
            // Deprecated: sales charts are strictly removed
        }
        window.switchSalesChartMode = switchSalesChartMode;

        function renderSalesTrendLineChart(trends, mode, companyFilter) {
            // Strictly concealed: sales trends are removed from dashboard
            return;

            destroyAnalyticsChart('sales_trend');

            trends = trends || (window.lastFleetAnalytics ? window.lastFleetAnalytics.sales_trends : null);
            if (!trends) return;

            mode = mode || window.currentSalesChartMode || 'DAY';
            companyFilter = companyFilter || window.selectedFleetCompany || 'ALL';

            const isDark = document.documentElement.classList.contains('dark');

            // 1. Update KPI badges
            const coTrends = trends.company_wise || {};
            const dayTrends = trends.day_wise || {};
            const monthTrends = trends.month_wise || {};

            const lgSales = (coTrends.totals && coTrends.totals[0] != null) ? Number(coTrends.totals[0]) : 0;
            const tgSales = (coTrends.totals && coTrends.totals[1] != null) ? Number(coTrends.totals[1]) : 0;
            const krSales = (coTrends.totals && coTrends.totals[2] != null) ? Number(coTrends.totals[2]) : 0;
            const totalSales = lgSales + tgSales + krSales;

            const totalEl = document.getElementById('sales-chart-total-val');
            if (totalEl) totalEl.textContent = '$' + Number(totalSales).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

            const lgEl = document.getElementById('sales-chart-lg-val');
            if (lgEl) lgEl.textContent = '$' + Number(lgSales).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

            const tgEl = document.getElementById('sales-chart-tg-val');
            if (tgEl) tgEl.textContent = '$' + Number(tgSales).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

            const krEl = document.getElementById('sales-chart-kreckle-val');
            if (krEl) krEl.textContent = '$' + Number(krSales).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

            // 2. Build chart data based on mode & company filter
            let labels = [];
            let datasets = [];

            const ctx = canvas.getContext('2d');
            function createGrad(c1, c2) {
                try {
                    const g = ctx.createLinearGradient(0, 0, 0, 300);
                    g.addColorStop(0, c1);
                    g.addColorStop(1, c2);
                    return g;
                } catch (e) {
                    return c1;
                }
            }

            if (mode === 'COMPANY') {
                // Multi-line comparison of all 3 companies side-by-side
                labels = dayTrends.labels || [];
                const gradLg = createGrad('rgba(59, 130, 246, 0.22)', 'rgba(59, 130, 246, 0.0)');
                const gradTg = createGrad('rgba(245, 158, 11, 0.22)', 'rgba(245, 158, 11, 0.0)');
                const gradKr = createGrad('rgba(16, 185, 129, 0.22)', 'rgba(16, 185, 129, 0.0)');

                datasets = [
                    {
                        label: 'LG Plast ($)',
                        data: dayTrends.lg_plast || [],
                        borderColor: '#3b82f6',
                        backgroundColor: gradLg,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#3b82f6'
                    },
                    {
                        label: 'Tagoneswa Hardware ($)',
                        data: dayTrends.tagoneswa || [],
                        borderColor: '#f59e0b',
                        backgroundColor: gradTg,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#f59e0b'
                    },
                    {
                        label: 'Kreckle Foods ($)',
                        data: dayTrends.kreckle || [],
                        borderColor: '#10b981',
                        backgroundColor: gradKr,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#10b981'
                    }
                ];
            } else if (mode === 'MONTH') {
                labels = monthTrends.labels || [];
                if (companyFilter !== 'ALL') {
                    const cLower = companyFilter.toLowerCase();
                    let subData = monthTrends.total || [];
                    let coLabel = 'Monthly Sales ($)';
                    let coColor = '#6366f1';

                    if (cLower.includes('lg')) {
                        subData = monthTrends.lg_plast || [];
                        coLabel = 'LG Plast Monthly Sales ($)';
                        coColor = '#3b82f6';
                    } else if (cLower.includes('tagoneswa') || cLower.includes('tg') || cLower.includes('hardware')) {
                        subData = monthTrends.tagoneswa || [];
                        coLabel = 'Tagoneswa Hardware Monthly Sales ($)';
                        coColor = '#f59e0b';
                    } else if (cLower.includes('kreckle')) {
                        subData = monthTrends.kreckle || [];
                        coLabel = 'Kreckle Foods Monthly Sales ($)';
                        coColor = '#10b981';
                    }

                    const grad = createGrad(coColor + '40', coColor + '00');
                    datasets = [{
                        label: coLabel,
                        data: subData,
                        borderColor: coColor,
                        backgroundColor: grad,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: 4,
                        pointHoverRadius: 7,
                        pointBackgroundColor: coColor
                    }];
                } else {
                    const gradTot = createGrad('rgba(99, 102, 241, 0.28)', 'rgba(99, 102, 241, 0.0)');
                    datasets = [{
                        label: 'Total Monthly Sales ($)',
                        data: monthTrends.total || [],
                        borderColor: '#6366f1',
                        backgroundColor: gradTot,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 7,
                        pointBackgroundColor: '#6366f1'
                    }];
                }
            } else {
                // DAY mode (Default)
                labels = dayTrends.labels || [];
                if (companyFilter !== 'ALL') {
                    const cLower = companyFilter.toLowerCase();
                    let subData = dayTrends.total || [];
                    let coLabel = 'Daily Sales ($)';
                    let coColor = '#10b981';

                    if (cLower.includes('lg')) {
                        subData = dayTrends.lg_plast || [];
                        coLabel = 'LG Plast Daily Sales ($)';
                        coColor = '#3b82f6';
                    } else if (cLower.includes('tagoneswa') || cLower.includes('tg') || cLower.includes('hardware')) {
                        subData = dayTrends.tagoneswa || [];
                        coLabel = 'Tagoneswa Hardware Daily Sales ($)';
                        coColor = '#f59e0b';
                    } else if (cLower.includes('kreckle')) {
                        subData = dayTrends.kreckle || [];
                        coLabel = 'Kreckle Foods Daily Sales ($)';
                        coColor = '#10b981';
                    }

                    const grad = createGrad(coColor + '40', coColor + '00');
                    datasets = [{
                        label: coLabel,
                        data: subData,
                        borderColor: coColor,
                        backgroundColor: grad,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 2.5,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: coColor
                    }];
                } else {
                    const gradTot = createGrad('rgba(16, 185, 129, 0.28)', 'rgba(16, 185, 129, 0.0)');
                    datasets = [{
                        label: 'Total Daily Sales ($)',
                        data: dayTrends.total || [],
                        borderColor: '#10b981',
                        backgroundColor: gradTot,
                        fill: true,
                        tension: 0.35,
                        borderWidth: 3,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#10b981'
                    }];
                }
            }

            window.analyticsCharts['sales_trend'] = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            display: mode === 'COMPANY',
                            position: 'top',
                            align: 'end',
                            labels: {
                                color: isDark ? '#d4d4d8' : '#334155',
                                boxWidth: 10,
                                boxHeight: 10,
                                usePointStyle: true,
                                font: { size: 11, weight: '600' }
                            }
                        },
                        tooltip: {
                            backgroundColor: isDark ? '#18181b' : '#ffffff',
                            titleColor: isDark ? '#f4f4f5' : '#0f172a',
                            bodyColor: isDark ? '#d4d4d8' : '#334155',
                            borderColor: isDark ? '#27272a' : '#e2e8f0',
                            borderWidth: 1,
                            padding: 10,
                            boxPadding: 4,
                            callbacks: {
                                label: function(ctx) {
                                    const val = Number(ctx.parsed.y || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                                    return ` ${ctx.dataset.label || ''}: $${val}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
                                display: true
                            },
                            ticks: {
                                color: isDark ? '#a1a1aa' : '#64748b',
                                font: { size: 10, weight: '600' },
                                maxRotation: 0,
                                autoSkip: true,
                                maxTicksLimit: 12
                            }
                        },
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'
                            },
                            ticks: {
                                color: isDark ? '#a1a1aa' : '#64748b',
                                font: { size: 10, weight: '600' },
                                callback: function(val) {
                                    if (val >= 1000) return '$' + (val / 1000).toFixed(1) + 'k';
                                    return '$' + val;
                                }
                            }
                        }
                    }
                }
            });
        }
        window.renderSalesTrendLineChart = renderSalesTrendLineChart;

        function renderAnalyticsSection(an, stats) {
            if (window.currentUserRole !== 'MASTER_ADMIN') return;
            if (!an && !stats) return;
            an = an || {};
            stats = stats || {};
            window.lastFleetAnalytics = an;
            window.lastFleetStats = stats;

            // 1. Top Executive KPI Cards
            const tripsTotalEl = document.getElementById('an-stat-trips-total');
            if (tripsTotalEl) tripsTotalEl.textContent = an.trips_total ?? stats.total_trips ?? 0;

            const tripsCompletedEl = document.getElementById('an-stat-trips-completed');
            if (tripsCompletedEl) tripsCompletedEl.textContent = `${an.trips_completed ?? 0} completed · ${an.trips_pending ?? 0} active`;

            const compEl = document.getElementById('an-stat-compliance');
            if (compEl) compEl.textContent = '100% Verified';

            const avgOpexEl = document.getElementById('an-stat-avg-opex');
            if (avgOpexEl) avgOpexEl.textContent = 'Avg Opex: $' + Number(an.avg_opex_per_trip || 0).toFixed(2);

            const utilEl = document.getElementById('an-stat-utilization');
            if (utilEl) utilEl.textContent = `${an.fleet_utilization_pct || 0}%`;

            const wsEl = document.getElementById('an-stat-ws-impact');
            if (wsEl) wsEl.textContent = `${an.workshop_impact_count || 0} trucks in workshop / service`;

            const recRateEl = document.getElementById('an-stat-recovery-rate');
            if (recRateEl) recRateEl.textContent = `${an.recovery_rate_pct || 0}%`;

            const recSubEl = document.getElementById('an-stat-recovery-sub');
            if (recSubEl) recSubEl.textContent = `$${Number(an.recovery_total || 0).toLocaleString()} recovered of $${Number(an.shortfall_total || 0).toLocaleString()}`;

            const isDark = document.documentElement.classList.contains('dark');

            // 2. Sales Trend Line Chart (Day-Wise, Month-Wise, Company-Wise)
            renderSalesTrendLineChart(an.sales_trends, window.currentSalesChartMode || 'DAY', window.selectedFleetCompany || 'ALL');

            // 3. Chart 1: Pipeline Stage Volume (Chart.js Bar Chart)
            const ctxPipeline = document.getElementById('an-pipeline-chart');
            if (ctxPipeline && typeof Chart !== 'undefined') {
                destroyAnalyticsChart('pipeline');
                const completed = an.trips_completed || 0;
                const active = Math.max(0, (an.trips_total || 0) - completed - (an.trips_cancelled || 0));
                const shortfalls = stats.shortfall_trips || 0;
                const approved = stats.approved_trips || 0;

                window.analyticsCharts['pipeline'] = new Chart(ctxPipeline, {
                    type: 'bar',
                    data: {
                        labels: ['Completed', 'Active/Transit', 'Shortfalls', 'Cleared'],
                        datasets: [{
                            label: 'Trip Volume',
                            data: [completed, active, shortfalls, approved],
                            backgroundColor: [
                                'rgba(16, 185, 129, 0.85)',
                                'rgba(59, 130, 246, 0.85)',
                                'rgba(245, 158, 11, 0.85)',
                                'rgba(99, 102, 241, 0.85)'
                            ],
                            borderRadius: 6,
                            borderWidth: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => ` ${ctx.parsed.y} trip(s)`
                                }
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: isDark ? '#a1a1aa' : '#64748b', font: { size: 10, weight: '600' } }
                            },
                            y: {
                                beginAtZero: true,
                                grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)' },
                                ticks: { color: isDark ? '#a1a1aa' : '#64748b', precision: 0 }
                            }
                        }
                    }
                });
            }

            // Pipeline Progress Bars
            const pipelineBarsEl = document.getElementById('an-pipeline-bars');
            if (pipelineBarsEl) {
                const totalT = an.trips_total || stats.total_trips || 1;
                const completed = an.trips_completed || 0;
                const active = Math.max(0, (an.trips_total || 0) - completed - (an.trips_cancelled || 0));
                const shortfalls = stats.shortfall_trips || 0;
                const approved = stats.approved_trips || 0;

                const stages = [
                    { label: 'Completed Deliveries', count: completed, color: 'bg-emerald-500' },
                    { label: 'Active / In-Transit Operations', count: active, color: 'bg-blue-500' },
                    { label: 'Shortfalls & Discrepancies Recorded', count: shortfalls, color: 'bg-amber-500' },
                    { label: 'Dispatches Cleared & Settled', count: approved, color: 'bg-indigo-500' }
                ];

                pipelineBarsEl.innerHTML = stages.map(s => {
                    const pct = Math.min(100, Math.round((s.count / totalT) * 100));
                    return `
                        <div>
                            <div class="flex justify-between text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">
                                <span>${s.label}</span>
                                <span class="font-mono text-slate-500">${s.count} trips (${pct}%)</span>
                            </div>
                            <div class="w-full bg-slate-100 dark:bg-[#181820] rounded-full h-2 overflow-hidden">
                                <div class="${s.color} h-2 rounded-full transition-all duration-500" style="width: ${pct}%"></div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            // 3. Chart 2: Operational Expense Composition (Chart.js Donut Chart)
            const ctxCost = document.getElementById('an-cost-donut-chart');
            if (ctxCost && typeof Chart !== 'undefined') {
                destroyAnalyticsChart('cost');
                const fuel = an.total_emergency_fuel || 0;
                const allowances = (an.total_allowances || 0) + (an.total_meals || 0);
                const accom = an.total_accommodation || 0;
                const other = (an.total_tolls || 0) + (an.total_emergency_other || 0);

                window.analyticsCharts['cost'] = new Chart(ctxCost, {
                    type: 'doughnut',
                    data: {
                        labels: ['Fuel', 'Allowances', 'Accommodation', 'Tolls/Other'],
                        datasets: [{
                            data: [fuel, allowances, accom, other],
                            backgroundColor: [
                                'rgba(245, 158, 11, 0.9)',
                                'rgba(59, 130, 246, 0.9)',
                                'rgba(168, 85, 247, 0.9)',
                                'rgba(244, 63, 94, 0.9)'
                            ],
                            borderWidth: isDark ? 2 : 1,
                            borderColor: isDark ? '#0a0a0d' : '#ffffff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '66%',
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: isDark ? '#d4d4d8' : '#334155',
                                    boxWidth: 8,
                                    boxHeight: 8,
                                    usePointStyle: true,
                                    font: { size: 10, weight: '600' }
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => ` $${Number(ctx.parsed).toLocaleString('en-US', {minimumFractionDigits: 2})}`
                                }
                            }
                        }
                    }
                });
            }

            // Expense Breakdown Bars
            const costBarsEl = document.getElementById('an-cost-bars');
            if (costBarsEl) {
                const totalOpex = an.total_operational_expenses || 1;
                const fuel = an.total_emergency_fuel || 0;
                const allowances = (an.total_allowances || 0) + (an.total_meals || 0);
                const accom = an.total_accommodation || 0;
                const other = (an.total_tolls || 0) + (an.total_emergency_other || 0);

                const costs = [
                    { label: 'Emergency Fuel Allocations', amount: fuel, color: 'bg-amber-500' },
                    { label: 'Driver Allowances & Meal Subsidies', amount: allowances, color: 'bg-blue-500' },
                    { label: 'Nightly Driver Accommodation', amount: accom, color: 'bg-purple-500' },
                    { label: 'Tollgates & Route Contingencies', amount: other, color: 'bg-rose-500' }
                ];

                costBarsEl.innerHTML = costs.map(c => {
                    const pct = totalOpex > 0 ? Math.min(100, Math.round((c.amount / totalOpex) * 100)) : 0;
                    return `
                        <div>
                            <div class="flex justify-between text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">
                                <span>${c.label}</span>
                                <span class="font-mono text-slate-500">$${Number(c.amount).toFixed(2)} (${pct}%)</span>
                            </div>
                            <div class="w-full bg-slate-100 dark:bg-[#181820] rounded-full h-2 overflow-hidden">
                                <div class="${c.color} h-2 rounded-full transition-all duration-500" style="width: ${pct}%"></div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            // 4. Chart 3: Top Corridors (Chart.js Horizontal Bar Chart)
            const ctxCorridors = document.getElementById('an-corridors-bar-chart');
            if (ctxCorridors && typeof Chart !== 'undefined') {
                destroyAnalyticsChart('corridors');
                const rawCities = (an.cities || []).slice(0, 6);
                const cLabels = rawCities.length > 0 ? rawCities.map(c => c.city) : ['Harare', 'Bulawayo', 'Mutare', 'Gweru', 'Masvingo'];
                const cCounts = rawCities.length > 0 ? rawCities.map(c => c.trips) : [0, 0, 0, 0, 0];

                window.analyticsCharts['corridors'] = new Chart(ctxCorridors, {
                    type: 'bar',
                    data: {
                        labels: cLabels,
                        datasets: [{
                            label: 'Trip Volume',
                            data: cCounts,
                            backgroundColor: 'rgba(99, 102, 241, 0.85)',
                            borderRadius: 6,
                            borderWidth: 0
                        }]
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => ` ${ctx.parsed.x} trip(s)`
                                }
                            }
                        },
                        scales: {
                            x: {
                                beginAtZero: true,
                                grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)' },
                                ticks: { color: isDark ? '#a1a1aa' : '#64748b', precision: 0 }
                            },
                            y: {
                                grid: { display: false },
                                ticks: { color: isDark ? '#d4d4d8' : '#334155', font: { size: 10, weight: '600' } }
                            }
                        }
                    }
                });
            }

            // Top Cities List
            const topCitiesEl = document.getElementById('an-top-cities-list');
            if (topCitiesEl) {
                const cities = an.cities || [];
                if (cities.length === 0) {
                    topCitiesEl.innerHTML = '<div class="text-xs text-slate-400 p-3 text-center">No city delivery records logged yet.</div>';
                } else {
                    topCitiesEl.innerHTML = cities.slice(0, 5).map(c => `
                        <div class="py-2 flex items-center justify-between text-xs">
                            <div>
                                <span class="font-bold text-slate-900 dark:text-zinc-100 capitalize">${c.city}</span>
                                <span class="text-[11px] text-slate-400 dark:text-zinc-500 ml-2 font-mono">${c.trips} trips</span>
                            </div>
                            <div class="font-mono font-bold text-slate-700 dark:text-zinc-300">
                                $${Number(c.sales || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                            </div>
                        </div>
                    `).join('');
                }
            }

            // 5. Chart 4: Financial Recovery / Fleet Readiness (Chart.js Donut Chart)
            const ctxFin = document.getElementById('an-financial-overview-chart');
            if (ctxFin && typeof Chart !== 'undefined') {
                destroyAnalyticsChart('financial');
                const cleared = Number(an.cleared_payments_total || 0);
                const debt = Number(an.outstanding_debt_total || stats.total_outstanding_backlog || 0);

                window.analyticsCharts['financial'] = new Chart(ctxFin, {
                    type: 'doughnut',
                    data: {
                        labels: ['Cleared Settlements', 'Outstanding Backlog'],
                        datasets: [{
                            data: [cleared, debt],
                            backgroundColor: [
                                'rgba(16, 185, 129, 0.9)',
                                'rgba(244, 63, 94, 0.9)'
                            ],
                            borderWidth: isDark ? 2 : 1,
                            borderColor: isDark ? '#0a0a0d' : '#ffffff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '70%',
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: isDark ? '#d4d4d8' : '#334155',
                                    boxWidth: 8,
                                    boxHeight: 8,
                                    usePointStyle: true,
                                    font: { size: 10, weight: '600' }
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => ` $${Number(ctx.parsed).toLocaleString('en-US', {minimumFractionDigits: 2})}`
                                }
                            }
                        }
                    }
                });
            }

            const ctxReadiness = document.getElementById('an-fleet-readiness-chart');
            if (ctxReadiness && typeof Chart !== 'undefined') {
                destroyAnalyticsChart('readiness');
                const avail = Number(stats.trucks_available ?? 39);
                const ws = Number(stats.trucks_in_workshop ?? 0);

                window.analyticsCharts['readiness'] = new Chart(ctxReadiness, {
                    type: 'doughnut',
                    data: {
                        labels: ['Available', 'In Workshop'],
                        datasets: [{
                            data: [avail, ws],
                            backgroundColor: [
                                'rgba(59, 130, 246, 0.9)',
                                'rgba(245, 158, 11, 0.9)'
                            ],
                            borderWidth: isDark ? 2 : 1,
                            borderColor: isDark ? '#0a0a0d' : '#ffffff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '70%',
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: isDark ? '#d4d4d8' : '#334155',
                                    boxWidth: 8,
                                    boxHeight: 8,
                                    usePointStyle: true,
                                    font: { size: 10, weight: '600' }
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => ` ${ctx.parsed} vehicles`
                                }
                            }
                        }
                    }
                });
            }

            const clearedTotEl = document.getElementById('an-cleared-total');
            if (clearedTotEl) clearedTotEl.textContent = '$' + Number(an.cleared_payments_total || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

            const debtTotEl = document.getElementById('an-outstanding-total');
            if (debtTotEl) debtTotEl.textContent = '$' + Number(an.outstanding_debt_total || stats.total_outstanding_backlog || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }

        // =============================================================
        // DYNAMIC DOMAIN-AWARE SIDEBAR CONTROLLER
        // =============================================================
        function updateSidebarForDomain(domain) {
            const nav = document.getElementById('sidebar-nav-container');
            if (!nav) return;

            let html = '';

            if (domain === 'fleet') {
                const canFuel = hasPermission('manage_fuel_price') || hasPermission('manage_city_minimums');
                const canTrucks = hasPermission('manage_trucks');
                const canDrivers = hasPermission('manage_drivers');
                const canSales = hasPermission('manage_sales_pipeline') || hasPermission('manage_sales_reps');
                const canAudit = hasPermission('view_audit_logs');
                const canUsers = currentUser && currentUser.role === 'MASTER_ADMIN';

                html = `
                    <div class="space-y-4">
                        <!-- Group 1: Commercial Operations -->
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                Commercial Operations
                            </div>
                            <div class="space-y-0.5">
                                <button onclick="switchFleetSubView('overview'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Operations Overview</span>
                                    <span class="text-[10px] font-mono text-slate-400">Live</span>
                                </button>
                                <button onclick="switchFleetSubView('trips'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Trip Pipeline</span>
                                    <span class="text-[10px] font-mono text-slate-400">7 Stages</span>
                                </button>
                                <button onclick="switchFleetSubView('trucks'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Fleet Vehicles</span>
                                    <span class="text-[10px] font-mono text-slate-400">Registry</span>
                                </button>
                                <button onclick="switchFleetSubView('drivers'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Commercial Drivers</span>
                                    <span class="text-[10px] font-mono text-slate-400">Roster</span>
                                </button>
                                <button onclick="switchFleetSubView('approvals'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Shortfall Approvals</span>
                                    <span class="text-[10px] font-mono text-amber-500 font-bold">Queue</span>
                                </button>
                                ${!canViewBalances && canSales ? `
                                <button onclick="switchFleetSubView('salespersons'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Sales Reps Directory</span>
                                    <span class="text-[10px] font-mono text-indigo-500 font-bold">Roster</span>
                                </button>` : ''}
                            </div>
                        </div>

                        <!-- Group 2: Finance & Ledgers (Restricted) -->
                        ${canViewBalances ? `
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                Finance & Ledgers
                            </div>
                            <div class="space-y-0.5">
                                <button onclick="switchFleetSubView('salespersons'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Sales Representative Balances</span>
                                    <span class="text-[10px] font-mono text-rose-500 font-bold">Balances</span>
                                </button>
                                <button onclick="switchFleetSubView('payments'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Payment History</span>
                                    <span class="text-[10px] font-mono text-emerald-500 font-bold">History</span>
                                </button>
                                <button onclick="switchFleetSubView('ledger'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Financial Audit Log</span>
                                    <span class="text-[10px] font-mono text-slate-400">Ledger</span>
                                </button>
                            </div>
                        </div>` : ''}

                        <!-- Group 3: Analytics & Insights -->
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                ${window.currentUserRole === 'MASTER_ADMIN' ? 'Analytics & Insights' : 'View Mode'}
                            </div>
                            <div class="space-y-0.5">
                                ${window.currentUserRole === 'MASTER_ADMIN' ? `
                                <button onclick="switchFleetSubView('analytics'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Data Analytics</span>
                                    <span class="text-[10px] font-bold text-blue-600 dark:text-blue-400">KPIs</span>
                                </button>` : ''}
                                <button onclick="switchFleetSubView('all'); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Consolidated View (All)</span>
                                    <span class="text-[10px] font-mono text-slate-400">Full</span>
                                </button>
                            </div>
                        </div>

                        <!-- Group 4: Operational Actions & Config -->
                        ${(canFuel || canTrucks || canDrivers || canSales || canAudit || canUsers) ? `
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                Operational Actions
                            </div>
                            <div class="space-y-0.5">
                                ${canFuel ? `
                                <button onclick="openCityConfigModal(); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Fuel & City Rates</span>
                                    <span class="text-[10px] font-mono text-slate-400">Config</span>
                                </button>` : ''}
                                ${canTrucks ? `
                                <button onclick="openAddTruckModal(); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Register Truck</span>
                                </button>` : ''}
                                ${canDrivers ? `
                                <button onclick="openAddDriverModal(); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Register Driver</span>
                                </button>` : ''}
                                ${canSales ? `
                                <button onclick="openAddSalesRepModal(); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">Register Sales Rep</span>
                                </button>` : ''}
                                ${canAudit ? `
                                <button onclick="openAuditLogsModal(); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">System Audit Logs</span>
                                </button>` : ''}
                                ${canUsers ? `
                                <button onclick="openUserManagementModal(); toggleSidebar(false);" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition cursor-pointer text-left">
                                    <span class="flex items-center gap-2">User Management & Permissions</span>
                                </button>` : ''}
                            </div>
                        </div>` : ''}
                    </div>
                `;
            } else if (domain === 'it') {
                html = `
                    <div class="space-y-4">
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                IT Helpdesk & Support
                            </div>
                            <div class="space-y-0.5">
                                <a href="#view-it" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2">Active Tickets Queue</span>
                                </a>
                                <a href="#view-it" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2">Critical & SLA Breaches</span>
                                </a>
                                <a href="#view-it" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2">WhatsApp Bot Diagnostics</span>
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            } else if (domain === 'projects') {
                html = `
                    <div class="space-y-4">
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                Construction & Projects
                            </div>
                            <div class="space-y-0.5">
                                <a href="#view-projects" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2">Active Site Projects</span>
                                </a>
                                <a href="#view-projects" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2">Materials & Cement Logistics</span>
                                </a>
                                <a href="#view-projects" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2">Site Budgets & Approvals</span>
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            } else if (domain === 'logistics') {
                html = `
                    <div class="space-y-4">
                        <div>
                            <div class="px-2.5 mb-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">
                                Workshop Fleet Maintenance
                            </div>
                            <div class="space-y-0.5">
                                <a href="#view-logistics" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2"><span>🔧</span> Active Service Jobs</span>
                                </a>
                                <a href="#view-logistics" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2"><span>⚙️</span> Awaiting Spares & Parts</span>
                                </a>
                                <a href="#view-logistics" onclick="toggleSidebar(false)" class="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition text-left">
                                    <span class="flex items-center gap-2"><span>🚦</span> Fleet Readiness Matrix</span>
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            }

            nav.innerHTML = html;
        }


        function filterByITAdmin(adminName) {
            const adminFilter = document.getElementById('it-admin-filter');
            if (adminFilter) {
                adminFilter.value = adminName;
            }
            itPage = 1;
            filterITTable(false);
            const tableCard = document.getElementById('it-table-card');
            if (tableCard) {
                tableCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            showToast(adminName === 'ALL' ? 'Showing all technician tickets' : `Filtered tickets for ${adminName}`);
        }

        function toggleTheme() {
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('tagoneswa_theme', isDark ? 'dark' : 'light');
            updateThemeUI(isDark);
        }

        function updateThemeUI(isDark) {
            document.querySelectorAll('.theme-toggle-icon').forEach(el => {
                el.textContent = isDark ? '☀️' : '🌙';
            });
            document.querySelectorAll('.theme-toggle-label').forEach(el => {
                el.textContent = isDark ? 'Light' : 'Dark';
            });
        }

        // Sync initial theme UI state
        updateThemeUI(document.documentElement.classList.contains('dark'));

        function showToast(msg, icon = '✅') {
            const toast = document.getElementById('toast');
            document.getElementById('toastMsg').textContent = msg;
            document.getElementById('toastIcon').textContent = icon;
            toast.classList.remove('translate-y-20', 'opacity-0');
            toast.classList.add('translate-y-0', 'opacity-100');
            setTimeout(() => {
                toast.classList.remove('translate-y-0', 'opacity-100');
                toast.classList.add('translate-y-20', 'opacity-0');
            }, 2500);
        }

        function switchDomain(domain) {
            const allowed = (cachedData && cachedData.user && cachedData.user.allowed_domains) || initialAllowedDomains;
            if (!allowed.includes(domain)) {
                domain = allowed[0] || initialDefaultTab;
            }

            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.domain-view').forEach(view => {
                view.classList.remove('active');
                view.style.display = 'none';
            });

            const targetBtn = document.getElementById('btn-tab-' + domain);
            const targetView = document.getElementById('view-' + domain);
            if (targetBtn) targetBtn.classList.add('active');
            if (targetView) {
                targetView.classList.add('active');
                targetView.style.display = 'block';
                window.location.hash = domain;
            }

            updateSidebarForDomain(domain);
        }

        async function manualRefresh() {
            if (isRefreshing) return;
            isRefreshing = true;

            const mIcon = document.getElementById('mobileRefreshIcon');
            const dIcon = document.getElementById('desktopRefreshIcon');
            if (mIcon) mIcon.classList.add('spinning');
            if (dIcon) dIcon.classList.add('spinning');

            try {
                await fetchDashboard();
                showToast('Live dashboard refreshed!');
            } catch (err) {
                showToast('Failed to refresh data', '⚠️');
            } finally {
                setTimeout(() => {
                    if (mIcon) mIcon.classList.remove('spinning');
                    if (dIcon) dIcon.classList.remove('spinning');
                    isRefreshing = false;
                }, 600);
            }
        }

        async function handleLogout() {
            try {
                await fetch('/api/logout', { method: 'POST' });
            } catch (e) {}
            window.location.href = '/login';
        }

        async function fetchDashboard() {
            try {
                const res = await fetch('/api/dashboard/data');
                if (res.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                const data = await res.json();
                cachedData = data;

                if (data.user) {
                    currentUser = data.user;
                    const uName = document.getElementById('userDisplayName');
                    if (uName) uName.textContent = data.user.name;
                    const uRole = document.getElementById('userRoleBadge');
                    if (uRole) uRole.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> ${data.user.role.replace('_', ' ')}`;
                }

                if (data.master_kpis) renderMasterKPIs(data.master_kpis);
                if (data.it) renderIT(data.it);
                if (data.projects) renderProjects(data.projects);
                if (data.logistics) renderLogistics(data.logistics);
                if (data.fleet) {
                    renderFleet(data.fleet);
                    switchFleetSubView(currentFleetSubView);
                }

                const allowed = (data.user && data.user.allowed_domains) || initialAllowedDomains;
                let hash = window.location.hash.replace('#', '');
                if (!allowed.includes(hash)) {
                    hash = allowed[0] || initialDefaultTab;
                }
                switchDomain(hash);
            } catch (err) {
                console.error('Error loading dashboard:', err);
            }
        }

        function renderIT(it) {
            if (!it) return;
            document.getElementById('it-stat-total').textContent = it.stats.total;
            document.getElementById('it-stat-active').textContent = it.stats.open + it.stats.in_progress;
            document.getElementById('it-stat-resolved').textContent = it.stats.resolved + it.stats.closed;
            document.getElementById('it-stat-avg-time').textContent = it.stats.avg_resolution;

            // Render IT Admin SLA Cards with click-to-filter
            const adminContainer = document.getElementById('it-admin-cards');
            if (adminContainer && it.admins) {
                adminContainer.innerHTML = it.admins.map(a => `
                    <div onclick="filterByITAdmin('${a.name}')" class="bg-slate-50 dark:bg-[#0f0f13] border border-slate-200 dark:border-zinc-800 rounded-xl p-3.5 sm:p-4 flex items-center justify-between shadow-xs hover:border-blue-500 dark:hover:border-blue-500/60 transition cursor-pointer hover:shadow-md group">
                        <div>
                            <div class="font-extrabold text-slate-900 dark:text-zinc-100 text-xs sm:text-sm group-hover:text-blue-600 dark:group-hover:text-blue-400 transition flex items-center gap-1.5">
                                <span>${a.name}</span>
                                <span class="text-[10px] text-blue-500 opacity-0 group-hover:opacity-100 transition font-semibold">Filter</span>
                            </div>
                            <div class="text-[10px] sm:text-[11px] text-slate-500 dark:text-zinc-400 font-mono">+${a.phone}</div>
                            <div class="mt-2 flex items-center gap-1.5">
                                <span class="bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 text-[10px] font-bold px-2 py-0.5 rounded">${a.pending} Pending</span>
                                <span class="bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded">${a.resolved} Solved</span>
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-sm sm:text-base font-extrabold text-blue-600 dark:text-blue-400 font-mono">${a.sla_pct}% SLA</div>
                            <div class="text-[10px] sm:text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Avg: ${a.avg_time}</div>
                        </div>
                    </div>
                `).join('');
            }

            // Populate Admin Filter
            const adminFilter = document.getElementById('it-admin-filter');
            if (adminFilter && it.records) {
                const currentSelected = adminFilter.value;
                const adminNames = [...new Set(it.records.map(r => r.assigned_admin))].filter(Boolean);
                adminFilter.innerHTML = '<option value="ALL">All Support Admins</option>' + adminNames.map(name => `
                    <option value="${name}" ${currentSelected === name ? 'selected' : ''}>${name}</option>
                `).join('');
            }

            // Render Category Issue Tree
            const treeContainer = document.getElementById('it-category-tree');
            if (treeContainer) {
                if (it.category_tree && it.category_tree.length > 0) {
                    treeContainer.innerHTML = it.category_tree.map(cat => `
                        <div class="border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden bg-slate-50/50 dark:bg-[#11192e]/40">
                            <div class="p-3 sm:p-3.5 bg-slate-100/80 dark:bg-[#15203b] font-extrabold text-xs text-slate-900 dark:text-white flex items-center justify-between">
                                <span>📁 ${cat.category_name}</span>
                                <span class="bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 px-2 py-0.5 rounded-full text-[10px] font-bold">${cat.count} tickets</span>
                            </div>
                            <div class="p-3 space-y-2 text-xs">
                                ${cat.subcategories.map(sub => `
                                    <div class="pl-2.5 sm:pl-3 border-l-2 border-slate-300 dark:border-slate-700">
                                        <div class="font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between text-xs">
                                            <span>↳ ${sub.subcategory_name}</span>
                                            <span class="text-slate-400 dark:text-slate-500 font-medium text-[11px]">${sub.count} logs</span>
                                        </div>
                                        <div class="pl-2.5 sm:pl-3 mt-1 space-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                                            ${sub.issues.map(iss => `
                                                <div class="flex items-center justify-between py-0.5">
                                                    <span>• ${iss.issue_name}</span>
                                                    <span class="font-mono text-slate-600 dark:text-slate-300 font-bold">${iss.count}</span>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `).join('');
                } else {
                    treeContainer.innerHTML = '<div class="text-xs text-slate-400 dark:text-slate-500 p-3">No category issues logged yet.</div>';
                }
            }

            filterITTable(false);
        }

        function filterITTable(resetPage = false) {
            if (!cachedData || !cachedData.it) return;
            if (resetPage) itPage = 1;

            const q = document.getElementById('it-search').value.toLowerCase().trim();
            const statusFilter = document.getElementById('it-status-filter').value;
            const adminFilter = document.getElementById('it-admin-filter').value;

            let records = cachedData.it.records.filter(r => {
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.employee_name.toLowerCase().includes(q) ||
                                 r.issue.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesAdmin = adminFilter === 'ALL' || r.assigned_admin === adminFilter;
                return matchesQ && matchesStatus && matchesAdmin;
            });

            // Enforce newest tickets first (descending order by ticket_id)
            records.sort((a, b) => (b.ticket_id || 0) - (a.ticket_id || 0));

            // Update Dynamic Count Badge
            document.getElementById('it-count-badge').textContent = `Showing ${records.length} of ${cachedData.it.records.length} tickets`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / itPageSize));
            if (itPage > totalPages) itPage = totalPages;
            const startIndex = (itPage - 1) * itPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + itPageSize);

            const tbody = document.getElementById('it-table-body');
            if (tbody) {
                if (records.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching IT support tickets found.</td></tr>';
                } else {
                    tbody.innerHTML = pagedRecords.map(r => {
                        let statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        let statusDot = 'bg-amber-500';
                        if (r.status === 'Resolved' || r.status === 'Closed') {
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        } else if (r.status === 'In Progress') {
                            statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                            statusDot = 'bg-blue-500 animate-pulse';
                        }

                        let pBadge = 'bg-slate-100 dark:bg-[#121216] text-slate-700 dark:text-zinc-300 border border-slate-200 dark:border-zinc-800';
                        if (r.priority === 'Urgent') pBadge = 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-500/30 font-bold';
                        else if (r.priority === 'High') pBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30 font-bold';

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${r.ticket_number}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${r.employee_name}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${r.employee_phone}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-700 dark:text-zinc-300 whitespace-nowrap">${r.department}<br><small class="text-slate-500 dark:text-zinc-400 font-medium">📍 ${r.location}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong class="text-slate-900 dark:text-zinc-100">${r.category}</strong> <span class="text-slate-400">➔</span> ${r.subcategory}<br><small class="text-slate-500 dark:text-zinc-400">${r.issue}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><span class="px-2 py-0.5 rounded text-[10px] ${pBadge}">${r.priority}</span></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${statusBadge} whitespace-nowrap">
                                        <span class="w-1.5 h-1.5 rounded-full ${statusDot}"></span>
                                        ${r.status}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${r.assigned_admin}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-slate-900 dark:text-zinc-100 whitespace-nowrap">${r.resolution_time}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            renderPaginationControls('it-pagination-info', 'it-pagination-controls', itPage, records.length, itPageSize, 'changeITPage');
        }

        function renderProjects(proj) {
            if (!proj) return;
            document.getElementById('proj-stat-total').textContent = proj.stats.total;
            document.getElementById('proj-stat-active').textContent = proj.stats.open + proj.stats.in_progress;
            document.getElementById('proj-stat-completed').textContent = proj.stats.resolved + proj.stats.closed;
            document.getElementById('proj-stat-locations').textContent = proj.stats.locations_count;

            // Populate Location & Admin Filter
            const locFilter = document.getElementById('proj-loc-filter');
            if (locFilter && proj.records) {
                const currentLoc = locFilter.value;
                const locations = [...new Set(proj.records.map(r => r.location))].filter(Boolean);
                locFilter.innerHTML = '<option value="ALL">All Branches & Yards</option>' + locations.map(loc => `
                    <option value="${loc}" ${currentLoc === loc ? 'selected' : ''}>${loc}</option>
                `).join('');
            }

            const adminFilter = document.getElementById('proj-admin-filter');
            if (adminFilter && proj.records) {
                const currentAdmin = adminFilter.value;
                const admins = [...new Set(proj.records.map(r => r.assigned_admin))].filter(Boolean);
                adminFilter.innerHTML = '<option value="ALL">All Project Leads</option>' + admins.map(a => `
                    <option value="${a}" ${currentAdmin === a ? 'selected' : ''}>${a}</option>
                `).join('');
            }

            filterProjectsTable(false);
        }

        function filterProjectsTable(resetPage = false) {
            if (!cachedData || !cachedData.projects) return;
            if (resetPage) projPage = 1;

            const q = document.getElementById('proj-search').value.toLowerCase().trim();
            const locFilter = document.getElementById('proj-loc-filter').value;
            const adminFilter = document.getElementById('proj-admin-filter').value;
            const statusFilter = document.getElementById('proj-status-filter').value;

            let records = cachedData.projects.records.filter(r => {
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.location.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesLoc = locFilter === 'ALL' || r.location === locFilter;
                const matchesAdmin = adminFilter === 'ALL' || r.assigned_admin === adminFilter;
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesLoc && matchesAdmin && matchesStatus;
            });

            // Enforce newest tickets first (descending order by ticket_id)
            records.sort((a, b) => (b.ticket_id || 0) - (a.ticket_id || 0));

            document.getElementById('proj-count-badge').textContent = `Showing ${records.length} of ${cachedData.projects.records.length} tickets`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / projPageSize));
            if (projPage > totalPages) projPage = totalPages;
            const startIndex = (projPage - 1) * projPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + projPageSize);

            const tbody = document.getElementById('proj-table-body');
            if (tbody) {
                if (records.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching project tickets found.</td></tr>';
                } else {
                    tbody.innerHTML = pagedRecords.map(r => {
                        let statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        let statusDot = 'bg-amber-500';
                        if (r.status === 'Resolved' || r.status === 'Closed') {
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        } else if (r.status === 'In Progress') {
                            statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                            statusDot = 'bg-blue-500 animate-pulse';
                        }

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${r.ticket_number}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${r.employee_name}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${r.employee_phone}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-bold text-slate-800 dark:text-zinc-200 whitespace-nowrap">📍 ${r.location}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong class="text-slate-900 dark:text-zinc-100">${r.category}</strong><br><small class="text-slate-500 dark:text-zinc-400">${r.description}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${statusBadge} whitespace-nowrap">
                                        <span class="w-1.5 h-1.5 rounded-full ${statusDot}"></span>
                                        ${r.status}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${r.assigned_admin}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-500 dark:text-zinc-400 font-mono text-[11px] whitespace-nowrap">${r.created_at}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            renderPaginationControls('proj-pagination-info', 'proj-pagination-controls', projPage, records.length, projPageSize, 'changeProjPage');
        }

        function renderLogistics(log) {
            if (!log) return;
            document.getElementById('ws-stat-fleet').textContent = log.fleet_count || 39;
            document.getElementById('ws-stat-review').textContent = log.stats.under_review;
            document.getElementById('ws-stat-floor').textContent = log.stats.in_workshop;
            document.getElementById('ws-stat-parts').textContent = log.stats.awaiting_parts;
            document.getElementById('ws-stat-qc').textContent = log.stats.awaiting_qc;

            // Populate Mechanics Filter
            const mechFilter = document.getElementById('ws-mech-filter');
            if (mechFilter && log.records) {
                const currentMech = mechFilter.value;
                const mechs = [...new Set(log.records.map(r => r.assigned_mechanic))].filter(Boolean);
                mechFilter.innerHTML = '<option value="ALL">All Mechanics</option>' + mechs.map(m => `
                    <option value="${m}" ${currentMech === m ? 'selected' : ''}>${m}</option>
                `).join('');
            }

            filterFleetTable(false);
        }

        function filterFleetTable(resetPage = false) {
            if (!cachedData || !cachedData.logistics) return;
            if (resetPage) wsPage = 1;

            const q = document.getElementById('ws-search').value.toLowerCase().trim();
            const statusFilter = document.getElementById('ws-status-filter').value;
            const mechFilter = document.getElementById('ws-mech-filter').value;

            let records = cachedData.logistics.records.filter(r => {
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.truck_number.toLowerCase().includes(q) ||
                                 r.plate_number.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesMech = mechFilter === 'ALL' || r.assigned_mechanic === mechFilter;
                return matchesQ && matchesStatus && matchesMech;
            });

            // Enforce newest tickets first (descending order by ticket_id)
            records.sort((a, b) => (b.ticket_id || 0) - (a.ticket_id || 0));

            document.getElementById('ws-count-badge').textContent = `Showing ${records.length} of ${cachedData.logistics.records.length} vehicles`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / wsPageSize));
            if (wsPage > totalPages) wsPage = totalPages;
            const startIndex = (wsPage - 1) * wsPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + wsPageSize);

            const tbody = document.getElementById('ws-table-body');
            if (tbody) {
                if (records.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching workshop records found.</td></tr>';
                } else {
                    tbody.innerHTML = pagedRecords.map(r => {
                        let statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        let statusDot = 'bg-blue-500';
                        const statusRaw = r.status || '';
                        const statusLabel = statusRaw.replace(/_/g, ' ');

                        if (statusRaw === 'UNDER_REVIEW') {
                            statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                            statusDot = 'bg-amber-500';
                        } else if (statusRaw === 'CLOSED') {
                            statusBadge = 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700';
                            statusDot = 'bg-zinc-400';
                        } else if (statusRaw === 'REWORK_REQUIRED') {
                            statusBadge = 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30';
                            statusDot = 'bg-rose-500 animate-pulse';
                        } else if (statusRaw === 'AWAITING_TEST') {
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        }

                        let qcResult = r.qc_result || 'Pending QC';
                        let qcClass = 'text-zinc-500 dark:text-zinc-400';
                        if (qcResult.toUpperCase().includes('PASS')) {
                            qcClass = 'text-emerald-600 dark:text-emerald-400 font-bold';
                        } else if (qcResult.toUpperCase().includes('FAIL') || qcResult.toUpperCase().includes('REWORK')) {
                            qcClass = 'text-rose-600 dark:text-rose-400 font-bold';
                        } else if (qcResult.toUpperCase().includes('PEND')) {
                            qcClass = 'text-amber-600 dark:text-amber-400 font-medium';
                        }

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${r.ticket_number}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">Truck #${r.truck_number}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">${r.plate_number}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${r.truck_model}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong class="text-slate-900 dark:text-zinc-100">${r.category}</strong><br><small class="text-slate-500 dark:text-zinc-400">${r.description.substring(0, 45)}...</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-700 dark:text-zinc-300 whitespace-nowrap">${r.logged_by}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${r.assigned_mechanic}</strong><br><small class="text-blue-600 dark:text-blue-400 font-semibold">ETA: ${r.eta}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><small class="bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 px-2 py-0.5 rounded font-medium">${r.parts_status}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-bold font-mono text-slate-900 dark:text-zinc-100 whitespace-nowrap">${r.costing}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <div class="flex flex-col items-start gap-1">
                                        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${statusBadge} whitespace-nowrap">
                                            <span class="w-1.5 h-1.5 rounded-full ${statusDot}"></span>
                                            ${statusLabel}
                                        </span>
                                        <span class="inline-flex items-center gap-1 text-[10px] font-mono text-zinc-500 dark:text-zinc-400 bg-slate-100 dark:bg-[#121216] px-2 py-0.5 rounded border border-slate-200 dark:border-zinc-800 whitespace-nowrap">
                                            QC: <strong class="${qcClass}">${qcResult}</strong>
                                        </span>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            renderPaginationControls('ws-pagination-info', 'ws-pagination-controls', wsPage, records.length, wsPageSize, 'changeWSPage');
        }

        let currentAuditTimeframe = 'ALL';

        function renderMasterKPIs(kpis) {
            if (!kpis) return;
            const elActive = document.getElementById('master-active-ops');
            if (elActive) elActive.textContent = (kpis.pending_approvals !== undefined) ? kpis.pending_approvals : (kpis.active_operations ?? 0);
            const elRate = document.getElementById('master-res-rate');
            if (elRate) elRate.textContent = kpis.resolution_rate_pct + '%';
            const elRev = document.getElementById('master-transport-revenue');
            if (elRev) elRev.textContent = '$' + Number(kpis.transport_revenue).toFixed(2);
            const elBacklog = document.getElementById('master-financial-backlog');
            if (elBacklog) elBacklog.textContent = '$' + Number(kpis.total_financial_backlog).toFixed(2);
        }

        function setAuditTimeframe(tf) {
            currentAuditTimeframe = tf;
            ledgerPage = 1;
            document.querySelectorAll('.audit-tf-btn').forEach(btn => {
                btn.classList.remove('bg-blue-600', 'text-white');
                btn.classList.add('text-slate-600', 'dark:text-zinc-300', 'hover:text-slate-900', 'dark:hover:text-white');
            });
            const activeBtn = document.getElementById('timeframe-btn-' + tf);
            if (activeBtn) {
                activeBtn.classList.add('bg-blue-600', 'text-white');
                activeBtn.classList.remove('text-slate-600', 'dark:text-zinc-300', 'hover:text-slate-900', 'dark:hover:text-white');
            }
            if (cachedData && cachedData.fleet) {
                filterLedgerTable(true);
            }
        }

        function renderFleet(fleet) {
            if (!fleet) return;
            // 0. Operations Overview & Analytics
            if (fleet.overview) renderOperationsOverview(fleet.overview, currentUser);
            if (fleet.analytics || fleet.stats) renderAnalyticsSection(fleet.analytics, fleet.stats);

            // 1. Top Stats Cards
            const tripsEl = document.getElementById('fleet-stat-trips');
            if (tripsEl) tripsEl.textContent = fleet.stats.total_trips;
            const salesValEl = document.getElementById('fleet-stat-sales-val');
            if (salesValEl) {
                if (canViewBalances) {
                    salesValEl.textContent = '$' + Number(fleet.stats.total_sales_value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' ERP Sales';
                } else {
                    salesValEl.textContent = 'Trips Logged';
                }
            }
            const approvedEl = document.getElementById('fleet-stat-approved');
            if (approvedEl) approvedEl.textContent = fleet.stats.approved_trips;
            const shortfallsEl = document.getElementById('fleet-stat-shortfalls');
            if (shortfallsEl) shortfallsEl.textContent = fleet.stats.shortfall_trips;
            const transportEl = document.getElementById('fleet-stat-transport');
            if (transportEl) transportEl.textContent = '$' + Number(fleet.stats.total_transport_charges).toFixed(2);
            const backlogEl = document.getElementById('fleet-stat-backlog');
            if (backlogEl) backlogEl.textContent = '$' + Number(fleet.stats.total_outstanding_backlog).toFixed(2);
            const pendingPill = document.getElementById('fleet-total-pending-pill');
            if (pendingPill) pendingPill.textContent = '$' + Number(fleet.stats.total_outstanding_backlog).toFixed(2);

            // 2. Salesperson Pending Balance & Audit Cards
            const spCardsContainer = document.getElementById('fleet-salesperson-cards');
            if (spCardsContainer && fleet.salespersons) {
                if (fleet.salespersons.length === 0) {
                    spCardsContainer.innerHTML = '<div class="text-xs text-slate-400 dark:text-zinc-500 p-3 col-span-full">No salesperson ledger records yet.</div>';
                } else {
                    spCardsContainer.innerHTML = fleet.salespersons.map(sp => {
                        let badgeClass = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                        let badgeText = 'Cleared / Healthy';
                        if (sp.risk_level === 'HIGH_ALERT') {
                            badgeClass = 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30 font-bold';
                            badgeText = 'High Debt Alert';
                        } else if (sp.risk_level === 'ACTIVE_PENDING') {
                            badgeClass = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30 font-semibold';
                            badgeText = 'Pending Recovery';
                        }

                        let comp = sp.company || 'Commercial Sales';
                        let compBadgeClass = 'bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300 border-slate-200 dark:border-zinc-700';
                        if (comp.includes('LG')) {
                            compBadgeClass = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        } else if (comp.includes('Tagoneswa') || comp.includes('TG')) {
                            compBadgeClass = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        } else if (comp.includes('Kreckle')) {
                            compBadgeClass = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                        }

                        const searchData = `${(sp.name || '').toLowerCase()} ${(sp.phone || '')} ${(sp.company || '').toLowerCase()}`;

                        return `
                            <div class="salesperson-card bg-slate-50 dark:bg-[#0f0f13] border border-slate-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col justify-between hover:shadow-md transition" data-company="${escapeJsAttr(comp)}" data-search="${escapeJsAttr(searchData)}">
                                <div>
                                    <div class="flex items-start justify-between gap-1">
                                        <div>
                                            <div class="font-extrabold text-slate-900 dark:text-zinc-100 text-sm flex items-center gap-1.5 flex-wrap">
                                                <span>${sp.name}</span>
                                            </div>
                                            <div class="flex items-center gap-1.5 mt-1">
                                                <span class="text-[9px] font-bold px-1.5 py-0.5 rounded-md border ${compBadgeClass}">${comp}</span>
                                                <span class="text-[11px] text-slate-500 dark:text-zinc-400 font-mono">+${sp.phone}</span>
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-1.5 shrink-0">
                                            <button onclick="openAddSalesRepModal('${sp.employee_id || ''}', '${escapeJsAttr(sp.name)}', '${sp.phone}', '${escapeJsAttr(sp.email)}', true, '${escapeJsAttr(comp)}', '${escapeJsAttr(sp.role || 'SALES_REP')}')" title="Edit Sales Rep" class="text-indigo-600 hover:text-indigo-800 dark:hover:text-indigo-400 px-2 py-0.5 rounded-md border border-indigo-200 dark:border-indigo-900/60 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition text-xs font-bold cursor-pointer">
                                                Edit
                                            </button>
                                            <button onclick="deleteSalesRep('${sp.phone}', '${escapeJsAttr(sp.name)}')" title="Remove Sales Rep" class="text-rose-600 hover:text-rose-800 dark:hover:text-rose-400 px-2 py-0.5 rounded-md border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition text-xs font-bold cursor-pointer">
                                                ✕
                                            </button>
                                            <span class="text-[10px] px-2 py-0.5 rounded-full border ${badgeClass} whitespace-nowrap">${badgeText}</span>
                                        </div>
                                    </div>
                                    ${(canViewBalances && !sp.hide_financials) ? `
                                    <div class="mt-3 bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-lg p-2.5">
                                        <div class="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500">Current Outstanding Debt</div>
                                        <div class="text-xl font-extrabold font-mono ${sp.net_balance > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'} mt-0.5">
                                            $${sp.net_balance.toFixed(2)}
                                        </div>
                                    </div>
                                    ` : `
                                    <div class="mt-3 bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-lg p-2.5">
                                        <div class="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500">Commercial Contact</div>
                                        <div class="text-xs font-semibold text-slate-700 dark:text-zinc-300 mt-1 flex items-center gap-1.5">
                                            <a href="https://wa.me/${sp.phone}" target="_blank" class="text-emerald-600 dark:text-emerald-400 hover:underline flex items-center gap-1">
                                                <span>💬 WhatsApp</span>
                                            </a>
                                            <span class="text-slate-300 dark:text-zinc-700">•</span>
                                            <span class="text-slate-500 dark:text-zinc-400">${sp.active !== false ? 'Active Roster' : 'Inactive'}</span>
                                        </div>
                                    </div>
                                    `}
                                </div>
                                ${(canViewBalances && !sp.hide_financials) ? `
                                <div class="mt-3 pt-2.5 border-t border-slate-200/80 dark:border-zinc-800/80 flex items-center justify-between text-[11px] text-slate-600 dark:text-zinc-400">
                                    <span>Accrued: <strong class="text-rose-600 dark:text-rose-400 font-mono">$${sp.total_shortfalls.toFixed(2)}</strong></span>
                                    <span>Recovered: <strong class="text-emerald-600 dark:text-emerald-400 font-mono">$${sp.total_recovered.toFixed(2)}</strong></span>
                                </div>
                                ` : `
                                <div class="mt-3 pt-2.5 border-t border-slate-200/80 dark:border-zinc-800/80 flex items-center justify-between text-[11px] text-slate-400 dark:text-zinc-500 italic">
                                    <span>Financials: Restricted</span>
                                    <span>Division: ${escapeJsAttr(comp)}</span>
                                </div>
                                `}
                                ${(canViewBalances && !sp.hide_financials && sp.net_balance > 0 && hasPermission('clear_sales_rep_debt')) ? `
                                    <button onclick="openClearPaymentModal('${sp.name}', '${sp.phone}', ${sp.net_balance})" class="mt-3 w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-1.5 px-3 rounded-lg text-xs transition flex items-center justify-center gap-1 shadow-xs cursor-pointer">
                                        Clear Debt Settlement
                                    </button>
                                ` : ''}
                            </div>
                        `;
                    }).join('');
                    if (typeof applySalespersonsFilter === 'function') applySalespersonsFilter();
                }
            }

            // 3. Populate City Filter dropdown
            const cityFilter = document.getElementById('fleet-city-filter');
            if (cityFilter && fleet.cities) {
                const curCity = cityFilter.value;
                cityFilter.innerHTML = '<option value="ALL">All Destination Cities</option>' + fleet.cities.map(c => `
                    <option value="${c}" ${curCity === c ? 'selected' : ''}>${c}</option>
                `).join('');
            }

            // 4. Render all Subviews & Modals
            filterTripsTable(false);
            filterTrucksTable(false);
            filterDriversTable(false);
            filterPaymentsTable(false);
            filterLedgerTable(false);
            filterFleetApprovalsTable(false);
            populatePaySalespersonDropdown(fleet.salespersons);
            if (fleet.route_rules) renderModalCityRules(fleet.route_rules);
        }

        let currentAuditMode = 'TRAIL';

        function setAuditMode(mode) {
            currentAuditMode = mode;
            ledgerPage = 1;
            document.querySelectorAll('.audit-mode-btn').forEach(btn => {
                btn.classList.remove('bg-blue-600', 'text-white');
                btn.classList.add('text-slate-600', 'dark:text-zinc-300', 'hover:text-slate-900', 'dark:hover:text-white');
            });
            const activeBtn = document.getElementById('audit-mode-btn-' + mode);
            if (activeBtn) {
                activeBtn.classList.add('bg-blue-600', 'text-white');
                activeBtn.classList.remove('text-slate-600', 'dark:text-zinc-300', 'hover:text-slate-900', 'dark:hover:text-white');
            }
            const thead = document.getElementById('fleet-ledger-table-head');
            if (thead) {
                if (mode === 'TRAIL') {
                    thead.innerHTML = `
                        <tr>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Timestamp</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Actor</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Event / Action</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Module / Ref</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Details & Remarks</th>
                        </tr>
                    `;
                } else {
                    thead.innerHTML = `
                        <tr>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Date</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Salesperson</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Trip Ref</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Transaction Type</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Amount</th>
                            <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Audit Details & Notes</th>
                        </tr>
                    `;
                }
            }
            if (cachedData && cachedData.fleet) {
                filterLedgerTable(true);
            }
        }

        function filterLedgerTable(resetPage = false) {
            if (!cachedData || !cachedData.fleet) return;
            if (resetPage) ledgerPage = 1;

            const todayStr = new Date().toISOString().substring(0, 10);
            const yesterdayObj = new Date();
            yesterdayObj.setDate(yesterdayObj.getDate() - 1);
            const yesterdayStr = yesterdayObj.toISOString().substring(0, 10);
            const sevenDaysAgo = new Date();
            sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

            const isMatchingTimeframe = (dateOnly) => {
                if (currentAuditTimeframe === 'TODAY') return dateOnly === todayStr;
                if (currentAuditTimeframe === 'YESTERDAY') return dateOnly === yesterdayStr;
                if (currentAuditTimeframe === 'WEEK') return new Date(dateOnly) >= sevenDaysAgo;
                return true;
            };

            // Metrics from ledger & approvals
            const rawLedger = cachedData.fleet.ledger || [];
            let paidTotal = 0;
            let deferredTotal = 0;
            let recoveredTotal = 0;
            let alertCount = 0;

            rawLedger.forEach(e => {
                if (isMatchingTimeframe(e.date_only)) {
                    if (e.is_recovery) recoveredTotal += Math.abs(e.amount);
                    else deferredTotal += e.amount;
                }
            });

            if (cachedData.fleet.records) {
                cachedData.fleet.records.forEach(r => {
                    if (isMatchingTimeframe(r.date_only)) {
                        paidTotal += (r.amount_charged_to_customer || 0);
                        if (!r.is_clean) alertCount += r.audit_flags.length;
                    }
                });
            }

            const elPaid = document.getElementById('audit-stat-customer-paid');
            if (elPaid) elPaid.textContent = '$' + paidTotal.toFixed(2);
            const elDef = document.getElementById('audit-stat-deferred');
            if (elDef) elDef.textContent = '$' + deferredTotal.toFixed(2);
            const elRec = document.getElementById('audit-stat-recovered');
            if (elRec) elRec.textContent = '$' + recoveredTotal.toFixed(2);
            const alertEl = document.getElementById('audit-stat-flags');
            const alertNote = document.getElementById('audit-stat-flags-note');
            if (alertEl) {
                alertEl.textContent = alertCount;
                if (alertCount > 0) {
                    alertEl.className = 'text-base sm:text-lg font-extrabold text-red-600 dark:text-red-400 font-mono mt-0.5';
                    if (alertNote) alertNote.innerHTML = '<span class="text-red-600 dark:text-red-400 font-bold">Discrepancy Found</span>';
                } else {
                    alertEl.className = 'text-base sm:text-lg font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5';
                    if (alertNote) alertNote.innerHTML = '<span class="text-emerald-600 dark:text-emerald-400 font-semibold">100% Math Match</span>';
                }
            }

            const tbody = document.getElementById('fleet-ledger-table-body');
            if (!tbody) return;

            if (currentAuditMode === 'TRAIL') {
                const audits = cachedData.fleet.audit_logs || [];
                const filteredAudits = audits.filter(al => isMatchingTimeframe(al.date_only));
                const totalPages = Math.max(1, Math.ceil(filteredAudits.length / ledgerPageSize));
                if (ledgerPage > totalPages) ledgerPage = totalPages;
                const startIndex = (ledgerPage - 1) * ledgerPageSize;
                const paged = filteredAudits.slice(startIndex, startIndex + ledgerPageSize);

                if (filteredAudits.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-slate-400 dark:text-zinc-500 font-medium text-xs">No audit events recorded for this timeframe.</td></tr>';
                } else {
                    tbody.innerHTML = paged.map(al => {
                        let catBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        if ((al.action || '').includes('PAYMENT') || (al.action || '').includes('CLEAR')) {
                            catBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                        } else if ((al.action || '').includes('USER') || (al.action || '').includes('PERMISSION')) {
                            catBadge = 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-500/30';
                        } else if ((al.action || '').includes('FUEL') || (al.action || '').includes('RATE')) {
                            catBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        }

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 text-slate-500 dark:text-zinc-400 font-mono text-[11px] whitespace-nowrap">${al.timestamp}</td>
                                <td class="px-4 sm:px-5 py-3 whitespace-nowrap">
                                    <strong class="text-slate-900 dark:text-zinc-100">${al.username}</strong><br>
                                    <small class="text-slate-400 dark:text-zinc-500 font-mono">${al.user_role}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold border ${catBadge} font-mono">
                                        ${(al.action || '').replace(/_/g, ' ')}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 font-mono text-slate-700 dark:text-zinc-300 text-xs whitespace-nowrap">
                                    ${al.module} <span class="text-slate-400 dark:text-zinc-500">${al.entity_id || ''}</span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 text-slate-600 dark:text-zinc-300">
                                    ${al.remarks || '--'}
                                </td>
                            </tr>
                        `;
                    }).join('');
                }
                renderPaginationControls('ledger-pagination-info', 'ledger-pagination-controls', ledgerPage, filteredAudits.length, ledgerPageSize, 'changeLedgerPage');
            } else {
                // Shortfall Ledger Entries mode
                const filtered = rawLedger.filter(e => isMatchingTimeframe(e.date_only));
                const totalPages = Math.max(1, Math.ceil(filtered.length / ledgerPageSize));
                if (ledgerPage > totalPages) ledgerPage = totalPages;
                const startIndex = (ledgerPage - 1) * ledgerPageSize;
                const pagedRecords = filtered.slice(startIndex, startIndex + ledgerPageSize);

                if (filtered.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-8 text-center text-slate-400 dark:text-zinc-500 font-medium text-xs">No shortfall deficit or recovery transactions in this timeframe.</td></tr>';
                } else {
                    tbody.innerHTML = pagedRecords.map(e => {
                        const isRec = e.is_recovery;
                        const amtClass = isRec ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-rose-600 dark:text-rose-400 font-bold';
                        const sign = isRec ? '-' : '+';
                        const typeBadge = isRec
                            ? '<span class="inline-flex items-center gap-1.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>SURPLUS RECOVERY</span>'
                            : '<span class="inline-flex items-center gap-1.5 bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>SHORTFALL DEFICIT</span>';

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 text-slate-500 dark:text-zinc-400 font-mono text-[11px] whitespace-nowrap">${e.created_at}</td>
                                <td class="px-4 sm:px-5 py-3 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${e.salesperson_name}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${e.salesperson_phone}</small></td>
                                <td class="px-4 sm:px-5 py-3 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${e.trip_id}</td>
                                <td class="px-4 sm:px-5 py-3 whitespace-nowrap">${typeBadge}</td>
                                <td class="px-4 sm:px-5 py-3 font-mono ${amtClass} whitespace-nowrap">${sign}$${Math.abs(e.amount).toFixed(2)}</td>
                                <td class="px-4 sm:px-5 py-3 text-slate-600 dark:text-zinc-300">${e.notes || '--'}</td>
                            </tr>
                        `;
                    }).join('');
                }
                renderPaginationControls('ledger-pagination-info', 'ledger-pagination-controls', ledgerPage, filtered.length, ledgerPageSize, 'changeLedgerPage');
            }
        }

        function filterFleetApprovalsTable(resetPage = false) {
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.records) return;
            if (resetPage) fleetPage = 1;

            const q = document.getElementById('fleet-search').value.toLowerCase().trim();
            const cityFilter = document.getElementById('fleet-city-filter').value;
            const statusFilter = document.getElementById('fleet-status-filter').value;

            let records = cachedData.fleet.records.filter(r => {
                const matchesQ = !q || r.trip_id.toLowerCase().includes(q) ||
                                 r.salesperson_name.toLowerCase().includes(q) ||
                                 r.salesperson_phone.toLowerCase().includes(q) ||
                                 r.destination_city.toLowerCase().includes(q) ||
                                 r.route.toLowerCase().includes(q);
                const matchesCity = cityFilter === 'ALL' || r.destination_city === cityFilter;
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;

                let matchesCompany = true;
                if (window.selectedFleetCompany && window.selectedFleetCompany !== 'ALL') {
                    const sel = window.selectedFleetCompany.toLowerCase();
                    const rComp = (r.company || '').toLowerCase();
                    matchesCompany = rComp.includes(sel) || sel.includes(rComp);
                    if (!matchesCompany && r.salesperson_phone && cachedData.fleet.salespersons) {
                        const sp = cachedData.fleet.salespersons.find(s => s.phone === r.salesperson_phone);
                        if (sp && sp.company) {
                            const spComp = sp.company.toLowerCase();
                            matchesCompany = spComp.includes(sel) || sel.includes(spComp);
                        }
                    }
                }

                return matchesQ && matchesCity && matchesStatus && matchesCompany;
            });

            // Enforce newest first
            records.sort((a, b) => (b.id || 0) - (a.id || 0));

            document.getElementById('fleet-count-badge').textContent = `Showing ${records.length} of ${cachedData.fleet.records.length} trips`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / fleetPageSize));
            if (fleetPage > totalPages) fleetPage = totalPages;
            const startIndex = (fleetPage - 1) * fleetPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + fleetPageSize);

            const tbody = document.getElementById('fleet-approvals-table-body');
            if (tbody) {
                if (records.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching trip approvals found.</td></tr>';
                } else {
                    tbody.innerHTML = pagedRecords.map(r => {
                        let statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        let statusDot = 'bg-blue-500';
                        if (r.status === 'APPROVED' || r.status === 'DISPATCHED') {
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        } else if (r.status === 'SHORTFALL_RECORDED') {
                            statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                            statusDot = 'bg-amber-500';
                        }

                        let auditBadge = '<span class="inline-flex items-center gap-1.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Verified Parity</span>';
                        if (!r.is_clean) {
                            auditBadge = `<span class="inline-flex items-center gap-1.5 bg-red-500/10 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap" title="${r.audit_flags.join('; ')}"><span class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse"></span>Audit Alert (${r.audit_flags.length})</span>`;
                        }

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${r.trip_id}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${r.salesperson_name}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${r.salesperson_phone}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><span class="font-bold text-slate-800 dark:text-zinc-200">${r.destination_city}</span><br><small class="text-slate-500 dark:text-zinc-400">${r.route}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono whitespace-nowrap">
                                    ${canViewBalances ? `
                                    <span class="font-bold ${r.trip_sales_value >= r.required_minimum ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-900 dark:text-zinc-100'}">$${r.trip_sales_value.toFixed(2)}</span>
                                    <br><small class="text-slate-400 dark:text-zinc-500">Min: $${r.required_minimum.toFixed(2)}</small>
                                    ` : `
                                    <span class="font-semibold text-slate-600 dark:text-zinc-400">Audited</span>
                                    `}
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono whitespace-nowrap">
                                    ${canViewBalances ? (r.has_shortfall ? `<span class="text-rose-600 dark:text-rose-400 font-bold">-$${r.shortfall.toFixed(2)}</span><br><small class="text-indigo-600 dark:text-indigo-400 font-bold">Fee: $${r.transport_charge.toFixed(2)}</small>` : '<span class="text-emerald-600 dark:text-emerald-400 font-bold">Compliant (No Fee)</span>') : (r.has_shortfall ? '<span class="text-amber-600 dark:text-amber-400 font-semibold">Shortfall Flagged</span>' : '<span class="text-emerald-600 dark:text-emerald-400 font-semibold">Compliant</span>')}
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-xs text-slate-700 dark:text-zinc-300 whitespace-nowrap">
                                    ${canViewBalances ? (r.has_shortfall ? `
                                        <span>Customer Paid: <strong class="text-emerald-700 dark:text-emerald-400 font-mono">$${r.amount_charged_to_customer.toFixed(2)}</strong></span><br>
                                        <span>Debt Added: <strong class="text-amber-700 dark:text-amber-400 font-mono">$${r.pending_balance_recorded.toFixed(2)}</strong></span>
                                    ` : '<span class="text-slate-400 dark:text-zinc-500">Direct Clearance</span>') : '<span class="text-slate-400 dark:text-zinc-500">Accounts Managed</span>'}
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">${auditBadge}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${statusBadge} whitespace-nowrap">
                                        <span class="w-1.5 h-1.5 rounded-full ${statusDot}"></span>
                                        ${r.status.replace(/_/g, ' ')}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-500 dark:text-zinc-400 text-[11px] font-mono whitespace-nowrap">${r.created_at}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            renderPaginationControls('fleet-pagination-info', 'fleet-pagination-controls', fleetPage, records.length, fleetPageSize, 'changeFleetPage');
        }

        // =============================================================
        // SUBVIEW 1: 7-STAGE COMMERCIAL TRIPS PIPELINE
        // =============================================================
        function filterTripsTable(resetPage = false) {
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.trips) return;
            if (resetPage) tripsPage = 1;

            const q = (document.getElementById('trips-search')?.value || '').toLowerCase().trim();
            const stageFilter = document.getElementById('trips-stage-filter')?.value || 'ALL';

            let trips = cachedData.fleet.trips.filter(t => {
                const matchesQ = !q || (t.trip_id && t.trip_id.toLowerCase().includes(q)) ||
                                 (t.salesperson_name && t.salesperson_name.toLowerCase().includes(q)) ||
                                 (t.salesperson_phone && t.salesperson_phone.toLowerCase().includes(q)) ||
                                 (t.destination_city && t.destination_city.toLowerCase().includes(q)) ||
                                 (t.truck_plate && t.truck_plate.toLowerCase().includes(q)) ||
                                 (t.driver_name && t.driver_name.toLowerCase().includes(q));
                
                let matchesStage = true;
                if (stageFilter !== 'ALL') {
                    const st = (t.status || '').toUpperCase();
                    matchesStage = st.includes(stageFilter);
                }

                let matchesCompany = true;
                if (window.selectedFleetCompany && window.selectedFleetCompany !== 'ALL') {
                    const sel = window.selectedFleetCompany.toLowerCase();
                    const tComp = (t.company || '').toLowerCase();
                    matchesCompany = tComp.includes(sel) || sel.includes(tComp);
                    if (!matchesCompany && t.salesperson_phone && cachedData.fleet.salespersons) {
                        const sp = cachedData.fleet.salespersons.find(s => s.phone === t.salesperson_phone);
                        if (sp && sp.company) {
                            const spComp = sp.company.toLowerCase();
                            matchesCompany = spComp.includes(sel) || sel.includes(spComp);
                        }
                    }
                }

                return matchesQ && matchesStage && matchesCompany;
            });

            const badgeEl = document.getElementById('trips-count-badge');
            if (badgeEl) badgeEl.textContent = `Showing ${trips.length} of ${cachedData.fleet.trips.length} trips`;

            const totalPages = Math.max(1, Math.ceil(trips.length / tripsPageSize));
            if (tripsPage > totalPages) tripsPage = totalPages;
            const startIndex = (tripsPage - 1) * tripsPageSize;
            const pagedTrips = trips.slice(startIndex, startIndex + tripsPageSize);

            const tbody = document.getElementById('fleet-trips-table-body');
            if (tbody) {
                if (trips.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching trips found in pipeline.</td></tr>';
                } else {
                    tbody.innerHTML = pagedTrips.map(t => {
                        const st = (t.status || '').toUpperCase();
                        let stageBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        let stageLabel = 'Stage 1: Quoted';

                        if (st.includes('APPROVED')) {
                            stageBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            stageLabel = 'Stage 2: Approved';
                        } else if (st.includes('VOUCHER') || st.includes('ALLOWANCE')) {
                            stageBadge = 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-500/30';
                            stageLabel = 'Stage 3: Voucher Issued';
                        } else if (st.includes('LOADED') || st.includes('ODOMETER')) {
                            stageBadge = 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/30';
                            stageLabel = 'Stage 4: Loaded';
                        } else if (st.includes('IN_TRANSIT') || st.includes('TRANSIT')) {
                            stageBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                            stageLabel = 'Stage 5: In Transit';
                        } else if (st.includes('OFFLOADED') || st.includes('POD')) {
                            stageBadge = 'bg-teal-500/10 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-500/30';
                            stageLabel = 'Stage 6: Offloaded';
                        } else if (st.includes('SETTLED') || st.includes('CLOSED')) {
                            stageBadge = 'bg-emerald-500/20 text-emerald-800 dark:text-emerald-200 border-emerald-300 dark:border-emerald-500/40';
                            stageLabel = 'Stage 7: Settled';
                        }

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${t.trip_id}</td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${stageBadge} whitespace-nowrap">
                                        ${stageLabel}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <strong class="text-slate-900 dark:text-zinc-100">${t.salesperson_name}</strong><br>
                                    <small class="text-slate-400 dark:text-zinc-500 font-mono">+${t.salesperson_phone}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <span class="font-bold text-slate-800 dark:text-zinc-200">${t.destination_city}</span><br>
                                    <small class="text-slate-500 dark:text-zinc-400">${t.route}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <strong class="text-slate-900 dark:text-zinc-100">${t.truck_plate}</strong><br>
                                    <small class="text-slate-500 dark:text-zinc-400">${t.driver_name}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap font-mono text-xs">
                                    <div>Allow: <strong class="text-slate-900 dark:text-zinc-100">$${t.total_allowance.toFixed(2)}</strong></div>
                                    <div>Transp: <strong class="text-indigo-600 dark:text-indigo-400">$${t.transport_charge.toFixed(2)}</strong></div>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap text-[11px] text-slate-500 dark:text-zinc-400 font-mono">
                                    <div>Dep: ${t.departed_at || '--'}</div>
                                    <div>Ret: ${t.returned_at || '--'}</div>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap font-mono text-xs">
                                    <span>${t.start_odometer ? t.start_odometer + ' km' : '--'} → ${t.end_odometer ? t.end_odometer + ' km' : '--'}</span>
                                    ${t.discrepancy_amount > 0 ? `<br><small class="text-rose-600 dark:text-rose-400 font-bold">Discrepancy: $${t.discrepancy_amount.toFixed(2)}</small>` : ''}
                                </td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            renderPaginationControls('trips-pagination-info', 'trips-pagination-controls', tripsPage, trips.length, tripsPageSize, 'changeTripsPage');
        }

        // =============================================================
        // SUBVIEW 4: FLEET VEHICLES
        // =============================================================
        function filterTrucksTable(resetPage = false) {
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.trucks) return;
            if (resetPage) trucksPage = 1;

            const q = (document.getElementById('trucks-search')?.value || '').toLowerCase().trim();
            let trucks = cachedData.fleet.trucks.filter(t => {
                return !q || (t.truck_number && t.truck_number.toLowerCase().includes(q)) ||
                             (t.plate_number && t.plate_number.toLowerCase().includes(q)) ||
                             (t.model_make && t.model_make.toLowerCase().includes(q)) ||
                             (t.body_type && t.body_type.toLowerCase().includes(q)) ||
                             (t.home_depot && t.home_depot.toLowerCase().includes(q));
            });

            const totalPages = Math.max(1, Math.ceil(trucks.length / trucksPageSize));
            if (trucksPage > totalPages) trucksPage = totalPages;
            const startIndex = (trucksPage - 1) * trucksPageSize;
            const pagedTrucks = trucks.slice(startIndex, startIndex + trucksPageSize);

            const tbody = document.getElementById('fleet-trucks-table-body');
            if (tbody) {
                if (trucks.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No commercial trucks found.</td></tr>';
                } else {
                    tbody.innerHTML = pagedTrucks.map(t => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                            <td class="px-4 sm:px-5 py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">#${t.truck_number}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-extrabold text-slate-900 dark:text-zinc-100 whitespace-nowrap">${t.plate_number}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${t.model_make}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-slate-600 dark:text-zinc-300 whitespace-nowrap">${t.body_type}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-slate-500 dark:text-zinc-400 whitespace-nowrap">${t.home_depot}</td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${t.active ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30' : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30'}">
                                    <span class="w-1.5 h-1.5 rounded-full ${t.active ? 'bg-emerald-500' : 'bg-rose-500'}"></span>
                                    ${t.active ? 'Commercial Ready' : 'Maintenance'}
                                </span>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 text-right whitespace-nowrap">
                                <div class="inline-flex items-center gap-1.5 justify-end">
                                    <button onclick="openAddTruckModal('${t.truck_id}', '${t.truck_number}', '${t.plate_number}', '${escapeJsAttr(t.model_make)}', '${t.body_type}', '${escapeJsAttr(t.home_depot)}', ${t.active})" class="text-blue-600 hover:text-blue-800 dark:hover:text-blue-400 font-bold text-xs px-2.5 py-1 rounded-lg border border-blue-200 dark:border-blue-900/60 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition cursor-pointer">
                                        Edit
                                    </button>
                                    ${hasPermission('manage_trucks') ? `
                                        <button onclick="deleteTruck('${t.truck_id}', '${t.truck_number}')" class="text-rose-600 hover:text-rose-800 dark:hover:text-rose-400 font-bold text-xs px-2.5 py-1 rounded-lg border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition cursor-pointer">
                                            Delete
                                        </button>
                                    ` : ''}
                                </div>
                            </td>
                        </tr>
                    `).join('');
                }
            }

            renderPaginationControls('trucks-pagination-info', 'trucks-pagination-controls', trucksPage, trucks.length, trucksPageSize, 'changeTrucksPage');
        }

        // =============================================================
        // SUBVIEW 5: COMMERCIAL DRIVERS
        // =============================================================
        function filterDriversTable(resetPage = false) {
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.drivers) return;
            if (resetPage) driversPage = 1;

            const q = (document.getElementById('drivers-search')?.value || '').toLowerCase().trim();
            let drivers = cachedData.fleet.drivers.filter(d => {
                return !q || (d.full_name && d.full_name.toLowerCase().includes(q)) ||
                             (d.phone && d.phone.toLowerCase().includes(q)) ||
                             (d.role && d.role.toLowerCase().includes(q));
            });

            const totalPages = Math.max(1, Math.ceil(drivers.length / driversPageSize));
            if (driversPage > totalPages) driversPage = totalPages;
            const startIndex = (driversPage - 1) * driversPageSize;
            const pagedDrivers = drivers.slice(startIndex, startIndex + driversPageSize);

            const tbody = document.getElementById('fleet-drivers-table-body');
            if (tbody) {
                if (drivers.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No drivers found.</td></tr>';
                } else {
                    tbody.innerHTML = pagedDrivers.map(d => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-xs text-slate-500 dark:text-zinc-400 whitespace-nowrap">#WD-${d.staff_id}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-extrabold text-slate-900 dark:text-zinc-100 whitespace-nowrap">${d.full_name}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-blue-600 dark:text-blue-400 whitespace-nowrap">+${d.phone}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-xs font-semibold text-slate-700 dark:text-zinc-300 whitespace-nowrap">${d.role}</td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${d.active ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30' : 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-200'}">
                                    <span class="w-1.5 h-1.5 rounded-full ${d.active ? 'bg-emerald-500' : 'bg-zinc-400'}"></span>
                                    ${d.active ? 'On Roster' : 'Off Duty'}
                                </span>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 text-right whitespace-nowrap">
                                <button onclick="openAddDriverModal('${d.staff_id}', '${escapeJsAttr(d.full_name)}', '${d.phone}', '${d.role}', ${d.active})" class="text-purple-600 hover:text-purple-800 dark:hover:text-purple-400 font-bold text-xs px-2.5 py-1 rounded-lg border border-purple-200 dark:border-purple-900/60 hover:bg-purple-50 dark:hover:bg-purple-950/30 transition cursor-pointer">
                                    Edit
                                </button>
                            </td>
                        </tr>
                    `).join('');
                }
            }

            renderPaginationControls('drivers-pagination-info', 'drivers-pagination-controls', driversPage, drivers.length, driversPageSize, 'changeDriversPage');
        }

        // =============================================================
        // SUBVIEW 3: PAYMENT HISTORY
        // =============================================================
        function filterPaymentsTable(resetPage = false) {
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.payments) return;
            if (resetPage) paymentsPage = 1;

            const q = (document.getElementById('payments-search')?.value || '').toLowerCase().trim();
            let payments = cachedData.fleet.payments.filter(p => {
                return !q || (p.salesperson_name && p.salesperson_name.toLowerCase().includes(q)) ||
                             (p.salesperson_phone && p.salesperson_phone.toLowerCase().includes(q)) ||
                             (p.reference_number && p.reference_number.toLowerCase().includes(q)) ||
                             (p.payment_method && p.payment_method.toLowerCase().includes(q)) ||
                             (p.recorded_by && p.recorded_by.toLowerCase().includes(q));
            });

            const totalPages = Math.max(1, Math.ceil(payments.length / paymentsPageSize));
            if (paymentsPage > totalPages) paymentsPage = totalPages;
            const startIndex = (paymentsPage - 1) * paymentsPageSize;
            const pagedPayments = payments.slice(startIndex, startIndex + paymentsPageSize);

            const tbody = document.getElementById('fleet-payments-table-body');
            if (tbody) {
                if (payments.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No payment clearances recorded yet.</td></tr>';
                } else {
                    tbody.innerHTML = pagedPayments.map(p => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-[11px] text-slate-500 dark:text-zinc-400 whitespace-nowrap">${p.payment_date}</td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <strong class="text-slate-900 dark:text-zinc-100">${p.salesperson_name}</strong><br>
                                <small class="text-slate-400 dark:text-zinc-500 font-mono">+${p.salesperson_phone}</small>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 font-mono font-bold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                                +$${p.cleared_amount.toFixed(2)}
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <span class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-[10px] font-bold px-2 py-0.5 rounded">
                                    ${p.payment_method}
                                </span>
                                <div class="text-[11px] font-mono text-slate-500 dark:text-zinc-400 mt-0.5">Ref: ${p.reference_number}</div>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-xs whitespace-nowrap">
                                <span class="text-slate-400">$${p.previous_balance.toFixed(2)}</span> → <strong class="text-slate-900 dark:text-zinc-100">$${p.remaining_balance.toFixed(2)}</strong>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 text-xs text-slate-700 dark:text-zinc-300 whitespace-nowrap">${p.recorded_by}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-xs text-slate-600 dark:text-zinc-300">${p.remarks || '--'}</td>
                        </tr>
                    `).join('');
                }
            }

            renderPaginationControls('payments-pagination-info', 'payments-pagination-controls', paymentsPage, payments.length, paymentsPageSize, 'changePaymentsPage');
        }

        // =============================================================
        // MODAL 1: DELIVERY CORRIDORS & CITY MINIMUMS
        // =============================================================
        function openCityConfigModal() {
            const modal = document.getElementById('cityMinimumsModal');
            if (!modal) return;
            if (cachedData && cachedData.fleet) {
                const fpInput = document.getElementById('modal-fuel-price');
                if (fpInput && cachedData.fleet.fuel_price) {
                    fpInput.value = Number(cachedData.fleet.fuel_price).toFixed(2);
                }
                const mealInput = document.getElementById('modal-meal-rate');
                if (mealInput && cachedData.fleet.meal_rate !== undefined) {
                    mealInput.value = Number(cachedData.fleet.meal_rate).toFixed(2);
                }
                const accomInput = document.getElementById('modal-accom-rate');
                if (accomInput && cachedData.fleet.accommodation_rate !== undefined) {
                    accomInput.value = Number(cachedData.fleet.accommodation_rate).toFixed(2);
                }
                const budgetInput = document.getElementById('modal-budget-pct');
                if (budgetInput && cachedData.fleet.expense_budget_pct !== undefined) {
                    budgetInput.value = (Number(cachedData.fleet.expense_budget_pct) * 100).toFixed(1);
                }
                const vanInput = document.getElementById('modal-van-surcharge');
                if (vanInput && cachedData.fleet.van_minimum_surcharge !== undefined) {
                    vanInput.value = Number(cachedData.fleet.van_minimum_surcharge).toFixed(2);
                }
                if (cachedData.fleet.route_rules) {
                    renderModalCityRules(cachedData.fleet.route_rules);
                }

                // Granular permission gating for controls
                const canFuel = hasPermission('manage_fuel_price');
                const canCity = hasPermission('manage_city_minimums');
                const canMeal = hasPermission('manage_meal_rate');
                const canAccom = hasPermission('manage_accommodation_rate');

                const fpBtn = document.getElementById('modal-save-fuel-btn');
                if (fpInput) fpInput.disabled = !canFuel;
                if (fpBtn) fpBtn.style.display = canFuel ? '' : 'none';

                if (mealInput) mealInput.disabled = !canMeal;
                if (accomInput) accomInput.disabled = !canAccom;
                if (budgetInput) budgetInput.disabled = !canFuel;
                if (vanInput) vanInput.disabled = !canCity;

                const opsBtn = document.getElementById('modal-save-ops-btn');
                if (opsBtn) opsBtn.style.display = (canMeal || canAccom || canFuel || canCity) ? '' : 'none';
            }
            modal.classList.remove('hidden');
            syncBodyScrollLock();
        }

        function closeCityConfigModal() {
            const modal = document.getElementById('cityMinimumsModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        let modalCityRulesCache = [];
        function renderModalCityRules(rules) {
            if (!rules) return;
            if (Array.isArray(rules)) {
                modalCityRulesCache = rules.map(c => ({
                    key: c.city_key || c.key || '',
                    city_name: c.city_name || c.city_key || c.key || '',
                    route: c.route || c.corridor || '--',
                    distance_km: c.distance_km,
                    min_sales: c.min_sales || 0,
                    van_min: c.van_min || 0,
                    ...c
                }));
            } else {
                modalCityRulesCache = Object.keys(rules).map(k => ({
                    key: k,
                    city_name: rules[k].city_name || k,
                    ...rules[k]
                }));
            }
            filterCityRulesModal();
        }

        function filterCityRulesModal() {
            const q = (document.getElementById('modal-city-search')?.value || '').toLowerCase().trim();
            const tbody = document.getElementById('modal-city-rules-tbody');
            if (!tbody) return;

            let filtered = modalCityRulesCache.filter(c => {
                const name = (c.city_name || c.key || '').toLowerCase();
                const route = (c.route || '').toLowerCase();
                return !q || name.includes(q) || route.includes(q);
            });

            const countEl = document.getElementById('modal-city-count');
            if (countEl) countEl.textContent = `${filtered.length} Cities`;

            if (filtered.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-4 text-center text-slate-400">No matching cities found.</td></tr>';
                return;
            }

            const canEditCity = hasPermission('manage_city_minimums');

            tbody.innerHTML = filtered.map(c => {
                const cityName = c.city_name || c.key || '--';
                const distVal = Number(c.distance_km);
                const distDisplay = (distVal && distVal > 0)
                    ? `${distVal.toFixed(0)} km`
                    : '<span class="text-slate-400 dark:text-zinc-500 italic text-[11px]">Not configured</span>';

                return `
                <tr class="hover:bg-slate-50 dark:hover:bg-[#16161e] transition">
                    <td class="px-4 py-2.5 font-bold text-slate-900 dark:text-zinc-100 capitalize">${cityName}</td>
                    <td class="px-4 py-2.5 text-[11px] text-slate-500 dark:text-zinc-400">${c.route || '--'}</td>
                    <td class="px-4 py-2.5 font-mono text-xs text-slate-700 dark:text-zinc-300">${distDisplay}</td>
                    <td class="px-4 py-2.5">
                        <div class="relative w-28">
                            <span class="absolute left-2 top-1 text-slate-400 text-xs">$</span>
                            <input type="number" step="0.01" id="min-input-${c.key}" value="${Number(c.min_sales || 0).toFixed(2)}" ${canEditCity ? '' : 'readonly disabled'} class="w-full pl-5 pr-2 py-1 bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-lg text-xs font-mono font-bold text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                        </div>
                    </td>
                    <td class="px-4 py-2.5">
                        <div class="relative w-28">
                            <span class="absolute left-2 top-1 text-slate-400 text-xs">$</span>
                            <input type="number" step="0.01" id="van-input-${c.key}" value="${Number(c.van_min || 0).toFixed(2)}" ${canEditCity ? '' : 'readonly disabled'} class="w-full pl-5 pr-2 py-1 bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-lg text-xs font-mono font-bold text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                        </div>
                    </td>
                    <td class="px-4 py-2.5 text-right">
                        ${canEditCity ? `
                        <button onclick="saveCityMin('${c.key}')" id="btn-save-${c.key}" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer">
                            Save
                        </button>
                        ` : '<span class="text-slate-400 text-[11px] font-medium">Read-Only</span>'}
                    </td>
                </tr>
                `;
            }).join('');
        }

        async function saveFuelPrice() {
            if (!hasPermission('manage_fuel_price')) {
                alert('Permission denied: You do not have permission to change fuel prices.');
                return;
            }
            const fpInput = document.getElementById('modal-fuel-price');
            const btn = document.getElementById('modal-save-fuel-btn');
            const feedback = document.getElementById('fuel-update-feedback');
            if (!fpInput || !btn) return;

            const newPrice = parseFloat(fpInput.value);
            if (isNaN(newPrice) || newPrice <= 0) {
                alert('Please enter a valid fuel price.');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '⏳ Recalculating 45 Cities...';
            if (feedback) feedback.classList.add('hidden');

            try {
                const res = await fetch('/api/v2/config/update-fuel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fuel_price: newPrice, recalculate_cities: true })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Fuel price updated to $${newPrice.toFixed(2)}/L and 45 cities recalculated!`);
                    if (feedback) {
                        feedback.textContent = `✅ Successfully recalculated all 45 cities based on $${newPrice.toFixed(2)}/L fuel rate`;
                        feedback.className = 'mt-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400 block';
                    }
                    await fetchDashboard();
                } else {
                    alert(data.detail || 'Failed to update fuel price');
                }
            } catch (err) {
                alert('Network error while updating fuel price: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span>💾</span> Save & Recalculate 45 Cities';
            }
        }

        async function saveCityMin(cityKey) {
            if (!hasPermission('manage_city_minimums')) {
                alert('Permission denied: You do not have permission to update city minimum sales.');
                return;
            }
            const minInput = document.getElementById('min-input-' + cityKey);
            const vanInput = document.getElementById('van-input-' + cityKey);
            const btn = document.getElementById('btn-save-' + cityKey);
            if (!minInput || !vanInput || !btn) return;

            const minSales = parseFloat(minInput.value);
            const vanMin = parseFloat(vanInput.value);
            btn.disabled = true;
            btn.textContent = '...';

            try {
                const res = await fetch('/api/v2/config/update-city-minimum', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ city_key: cityKey, min_sales: minSales, van_min: vanMin })
                });
                if (res.ok) {
                    btn.textContent = '✅ Saved';
                    btn.className = 'bg-emerald-600 text-white font-bold px-3 py-1 rounded-lg text-[11px] transition shadow-xs';
                    setTimeout(() => {
                        btn.textContent = 'Save';
                        btn.className = 'bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer';
                        btn.disabled = false;
                    }, 2000);
                    showToast(`Updated threshold for ${cityKey.toUpperCase()}!`);
                    await fetchDashboard();
                } else {
                    btn.disabled = false;
                    btn.textContent = 'Save';
                    alert('Failed to save city minimum threshold.');
                }
            } catch (err) {
                btn.disabled = false;
                btn.textContent = 'Save';
                alert('Network error: ' + err.message);
            }
        }

        // =============================================================
        // MODAL 2: CLEAR SALES REP DEBT SETTLEMENT
        // =============================================================
        let activeSalespersonsForPay = [];
        function populatePaySalespersonDropdown(salespersons) {
            if (!salespersons) return;
            activeSalespersonsForPay = salespersons;
            const selectEl = document.getElementById('modal-pay-salesperson');
            if (!selectEl) return;

            const currentVal = selectEl.value;
            selectEl.innerHTML = '<option value="">-- Choose Sales Rep --</option>' + salespersons.map(sp => `
                <option value="${sp.phone}" data-name="${sp.name}" data-balance="${sp.net_balance}">
                    ${sp.name} (+${sp.phone}) — Debt: $${sp.net_balance.toFixed(2)}
                </option>
            `).join('');

            if (currentVal) selectEl.value = currentVal;
        }

        function openClearPaymentModal(repName = '', repPhone = '', balance = 0) {
            if (!hasPermission('clear_sales_rep_debt')) {
                alert('Permission denied: You do not have permission to clear sales rep debt.');
                return;
            }
            const modal = document.getElementById('clearPaymentModal');
            if (!modal) return;
            const selectEl = document.getElementById('modal-pay-salesperson');
            const amountInput = document.getElementById('modal-pay-amount');
            const refInput = document.getElementById('modal-pay-ref');
            const remarksInput = document.getElementById('modal-pay-remarks');
            const feedback = document.getElementById('modal-pay-feedback');

            if (feedback) feedback.classList.add('hidden');
            if (refInput) refInput.value = '';
            if (remarksInput) remarksInput.value = '';

            if (repPhone && selectEl) {
                selectEl.value = repPhone;
            }
            onSelectPaySalesperson();

            if (balance > 0 && amountInput) {
                amountInput.value = balance.toFixed(2);
            }

            modal.classList.remove('hidden');
            syncBodyScrollLock();
        }

        function closeClearPaymentModal() {
            const modal = document.getElementById('clearPaymentModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        function onSelectPaySalesperson() {
            const selectEl = document.getElementById('modal-pay-salesperson');
            const balanceEl = document.getElementById('modal-pay-current-balance');
            const amountInput = document.getElementById('modal-pay-amount');
            if (!selectEl || !balanceEl) return;

            const selectedOption = selectEl.options[selectEl.selectedIndex];
            if (selectedOption && selectedOption.dataset.balance) {
                const bal = parseFloat(selectedOption.dataset.balance);
                balanceEl.textContent = '$' + bal.toFixed(2);
                if (amountInput && (!amountInput.value || parseFloat(amountInput.value) <= 0)) {
                    amountInput.value = bal > 0 ? bal.toFixed(2) : '0.00';
                }
            } else {
                balanceEl.textContent = '$0.00';
            }
        }

        function fillFullClearance() {
            const selectEl = document.getElementById('modal-pay-salesperson');
            const amountInput = document.getElementById('modal-pay-amount');
            if (!selectEl || !amountInput) return;
            const selectedOption = selectEl.options[selectEl.selectedIndex];
            if (selectedOption && selectedOption.dataset.balance) {
                amountInput.value = parseFloat(selectedOption.dataset.balance).toFixed(2);
            }
        }

        async function submitClearPayment() {
            const selectEl = document.getElementById('modal-pay-salesperson');
            const amountInput = document.getElementById('modal-pay-amount');
            const methodSelect = document.getElementById('modal-pay-method');
            const refInput = document.getElementById('modal-pay-ref');
            const remarksInput = document.getElementById('modal-pay-remarks');
            const btn = document.getElementById('modal-submit-pay-btn');
            const feedback = document.getElementById('modal-pay-feedback');

            if (!selectEl.value) {
                alert('Please select a sales representative.');
                return;
            }
            const amt = parseFloat(amountInput.value);
            if (isNaN(amt) || amt <= 0) {
                alert('Please enter a valid amount greater than $0.00');
                return;
            }

            const selectedOption = selectEl.options[selectEl.selectedIndex];
            const repPhone = selectEl.value;
            const repName = selectedOption.dataset.name || 'Sales Rep';
            const method = methodSelect.value;
            const ref = (refInput.value || '').trim();
            const remarks = (remarksInput.value || '').trim();

            btn.disabled = true;
            btn.innerHTML = '⏳ Processing Clearance...';

            try {
                const res = await fetch('/api/v2/finance/clear-sales-rep-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        salesperson_phone: repPhone,
                        salesperson_name: repName,
                        cleared_amount: amt,
                        payment_method: method,
                        reference_number: ref,
                        remarks: remarks
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Successfully cleared $${amt.toFixed(2)} for ${repName}!`);
                    closeClearPaymentModal();
                    await fetchDashboard();
                } else {
                    if (feedback) {
                        feedback.textContent = data.detail || 'Error clearing payment';
                        feedback.className = 'text-xs font-bold text-rose-600 block';
                    } else {
                        alert(data.detail || 'Error clearing payment');
                    }
                }
            } catch (err) {
                alert('Network error while recording payment: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span>✅</span> Confirm Debt Clearance';
            }
        }

        // =============================================================
        // MODAL 3: SYSTEM AUDIT LOGS TRAIL
        // =============================================================
        function openAuditLogsModal() {
            const modal = document.getElementById('auditLogsModal');
            if (!modal) return;
            modal.classList.remove('hidden');
            syncBodyScrollLock();
            loadAuditLogs();
        }

        function closeAuditLogsModal() {
            const modal = document.getElementById('auditLogsModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        async function loadAuditLogs() {
            const tbody = document.getElementById('modal-audit-tbody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400">Loading audit records...</td></tr>';

            try {
                const res = await fetch('/api/v2/audit/logs');
                const data = await res.json();
                if (res.ok && data.logs) {
                    if (data.logs.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400">No audit logs found yet.</td></tr>';
                    } else {
                        tbody.innerHTML = data.logs.map(l => {
                            let actionColor = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                            if (l.action.includes('CLEAR')) actionColor = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            else if (l.action.includes('UPDATE')) actionColor = 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/30';

                            return `
                                <tr class="hover:bg-slate-50 dark:hover:bg-[#16161e] transition">
                                    <td class="px-4 py-2.5 font-mono text-[11px] text-slate-500 dark:text-zinc-400 whitespace-nowrap">${l.created_at}</td>
                                    <td class="px-4 py-2.5 whitespace-nowrap">
                                        <strong class="text-slate-900 dark:text-zinc-100">${l.username}</strong><br>
                                        <small class="text-slate-400 dark:text-zinc-500">${l.user_role}</small>
                                    </td>
                                    <td class="px-4 py-2.5 whitespace-nowrap">
                                        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold border ${actionColor} whitespace-nowrap">
                                            ${l.action}
                                        </span>
                                    </td>
                                    <td class="px-4 py-2.5 font-mono text-xs font-semibold text-slate-700 dark:text-zinc-300 whitespace-nowrap">${l.module}</td>
                                    <td class="px-4 py-2.5 font-mono text-xs text-slate-600 dark:text-zinc-400 whitespace-nowrap">${l.entity_id}</td>
                                    <td class="px-4 py-2.5 text-xs text-slate-700 dark:text-zinc-300">
                                        <div>${l.remarks || '--'}</div>
                                        ${l.new_value ? `<small class="font-mono text-slate-400 dark:text-zinc-500 block truncate max-w-xs">${JSON.stringify(l.new_value)}</small>` : ''}
                                    </td>
                                </tr>
                            `;
                        }).join('');
                    }
                }
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-4 text-center text-rose-500">Failed to load audit logs: ${err.message}</td></tr>`;
            }
        }

        // =============================================================
        // MODAL 1B: OPERATIONAL RATES & SURCHARGES
        // =============================================================
        async function saveOperationalParams() {
            if (!hasPermission('manage_meal_rate') && !hasPermission('manage_accommodation_rate') && !hasPermission('manage_fuel_price') && !hasPermission('manage_city_minimums')) {
                alert('Permission denied: You do not have permission to edit operational rates.');
                return;
            }
            const mealInput = document.getElementById('modal-meal-rate');
            const accomInput = document.getElementById('modal-accom-rate');
            const budgetInput = document.getElementById('modal-budget-pct');
            const vanInput = document.getElementById('modal-van-surcharge');
            const btn = document.getElementById('modal-save-rates-btn');
            const feedback = document.getElementById('rates-update-feedback');
            if (!mealInput || !accomInput || !budgetInput || !vanInput || !btn) return;

            const mealRate = parseFloat(mealInput.value);
            const accomRate = parseFloat(accomInput.value);
            const budgetPct = parseFloat(budgetInput.value) / 100.0;
            const vanSurcharge = parseFloat(vanInput.value);

            if (isNaN(mealRate) || isNaN(accomRate) || isNaN(budgetPct) || isNaN(vanSurcharge)) {
                alert('Please enter valid numeric values for all operational rates.');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '⏳ Saving Rates...';
            if (feedback) feedback.classList.add('hidden');

            try {
                const res = await fetch('/api/v2/config/update-operational-params', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        meal_rate: mealRate,
                        accommodation_rate: accomRate,
                        expense_budget_pct: budgetPct,
                        van_minimum_surcharge: vanSurcharge
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast('Operational rates updated successfully!');
                    if (feedback) {
                        feedback.textContent = '✅ Operational allowances and parameters updated in system cache';
                        feedback.className = 'mt-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400 block';
                    }
                    await fetchDashboard();
                } else {
                    alert(data.detail || 'Failed to update operational parameters');
                }
            } catch (err) {
                alert('Network error while updating operational rates: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span>💾</span> Save Rates & Surcharges';
            }
        }

        // =============================================================
        // MODAL 4: COMMERCIAL TRUCKS MANAGEMENT
        // =============================================================
        function openAddTruckModal(truckId = '', truckNum = '', plate = '', make = '', body = 'Horse', depot = 'Harare Central', active = true) {
            const modal = document.getElementById('addTruckModal');
            if (!modal) return;
            document.getElementById('modal-truck-id').value = truckId || '';
            document.getElementById('truck-modal-title').textContent = truckId ? ('Edit Commercial Truck #' + truckNum) : 'Register New Commercial Truck';
            document.getElementById('modal-truck-number').value = truckNum || '';
            document.getElementById('modal-truck-plate').value = plate || '';
            document.getElementById('modal-truck-make').value = make || '';
            document.getElementById('modal-truck-body').value = body || 'Horse';
            document.getElementById('modal-truck-depot').value = depot || 'Harare Central';
            document.getElementById('modal-truck-active').checked = (active === true || active === 'true');

            const fb = document.getElementById('modal-truck-feedback');
            if (fb) fb.classList.add('hidden');
            modal.classList.remove('hidden');
            syncBodyScrollLock();
        }

        function closeAddTruckModal() {
            const modal = document.getElementById('addTruckModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        async function submitSaveTruck() {
            const truckId = document.getElementById('modal-truck-id').value;
            const truckNum = (document.getElementById('modal-truck-number').value || '').trim();
            const plate = (document.getElementById('modal-truck-plate').value || '').trim();
            const make = (document.getElementById('modal-truck-make').value || '').trim();
            const body = document.getElementById('modal-truck-body').value;
            const depot = (document.getElementById('modal-truck-depot').value || '').trim();
            const active = document.getElementById('modal-truck-active').checked;
            const btn = document.getElementById('modal-submit-truck-btn');
            const fb = document.getElementById('modal-truck-feedback');

            if (!truckNum || !plate) {
                alert('Please provide both Truck Number and Plate Number.');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '⏳ Saving Truck...';

            try {
                const res = await fetch('/api/v2/fleet/trucks/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        truck_id: truckId ? parseInt(truckId) : null,
                        truck_number: truckNum,
                        plate_number: plate,
                        model_make: make,
                        body_type: body,
                        home_depot: depot,
                        active: active
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Truck ${truckNum} (${plate}) saved successfully!`);
                    closeAddTruckModal();
                    await fetchDashboard();
                } else {
                    if (fb) {
                        fb.textContent = data.detail || 'Failed to save truck';
                        fb.className = 'text-xs font-bold text-rose-600 block';
                    } else {
                        alert(data.detail || 'Failed to save truck');
                    }
                }
            } catch (err) {
                alert('Network error saving truck: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Save Truck Details';
            }
        }

        async function deleteTruck(truckId, truckNum) {
            if (!confirm(`Are you sure you want to remove truck #${truckNum} from the commercial fleet database? This action cannot be undone.`)) {
                return;
            }
            try {
                const res = await fetch('/api/v2/fleet/trucks/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ truck_id: parseInt(truckId) })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Truck #${truckNum} removed successfully.`);
                    await fetchDashboard();
                } else {
                    alert(data.detail || 'Failed to remove truck.');
                }
            } catch (err) {
                alert('Network error removing truck: ' + err.message);
            }
        }

        // =============================================================
        // MODAL 5: COMMERCIAL DRIVERS MANAGEMENT
        // =============================================================
        function openAddDriverModal(staffId = '', name = '', phone = '', role = 'COMMERCIAL DRIVER', active = true) {
            const modal = document.getElementById('addDriverModal');
            if (!modal) return;
            document.getElementById('modal-driver-id').value = staffId || '';
            document.getElementById('driver-modal-title').textContent = staffId ? ('Edit Commercial Driver: ' + name) : 'Register New Commercial Driver';
            document.getElementById('modal-driver-name').value = name || '';
            document.getElementById('modal-driver-phone').value = phone || '';
            document.getElementById('modal-driver-role').value = role || 'COMMERCIAL DRIVER';
            document.getElementById('modal-driver-active').checked = (active === true || active === 'true');

            const fb = document.getElementById('modal-driver-feedback');
            if (fb) fb.classList.add('hidden');
            modal.classList.remove('hidden');
            syncBodyScrollLock();
        }

        function closeAddDriverModal() {
            const modal = document.getElementById('addDriverModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        async function submitSaveDriver() {
            const staffId = document.getElementById('modal-driver-id').value;
            const name = (document.getElementById('modal-driver-name').value || '').trim();
            const phone = (document.getElementById('modal-driver-phone').value || '').trim();
            const role = document.getElementById('modal-driver-role').value;
            const active = document.getElementById('modal-driver-active').checked;
            const btn = document.getElementById('modal-submit-driver-btn');
            const fb = document.getElementById('modal-driver-feedback');

            if (!name || !phone) {
                alert('Please enter full legal name and WhatsApp phone number.');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = 'Saving Driver...';

            try {
                const res = await fetch('/api/v2/fleet/drivers/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        staff_id: staffId ? parseInt(staffId) : null,
                        full_name: name,
                        phone: phone,
                        role: role,
                        active: active
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Driver ${name} saved successfully!`);
                    closeAddDriverModal();
                    await fetchDashboard();
                } else {
                    if (fb) {
                        fb.textContent = data.detail || 'Failed to save driver';
                        fb.className = 'text-xs font-bold text-rose-600 block';
                    } else {
                        alert(data.detail || 'Failed to save driver');
                    }
                }
            } catch (err) {
                alert('Network error saving driver: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Save Driver';
            }
        }

        // =============================================================
        // MODAL 6: SALES REPRESENTATIVE MANAGEMENT
        // =============================================================
        function openAddSalesRepModal(empId = '', name = '', phone = '', email = '', active = true, company = '', role = 'SALES_REP') {
            const modal = document.getElementById('addSalesRepModal');
            if (!modal) return;
            document.getElementById('modal-salesrep-id').value = empId || '';
            document.getElementById('salesrep-modal-title').textContent = empId ? ('Edit: ' + name) : 'Register New Sales Rep / Admin';
            document.getElementById('modal-salesrep-name').value = name || '';
            document.getElementById('modal-salesrep-phone').value = phone || '';
            document.getElementById('modal-salesrep-email').value = email || '';
            document.getElementById('modal-salesrep-active').checked = (active === true || active === 'true');

            const compSelect = document.getElementById('modal-salesrep-company');
            if (compSelect) {
                if (company) {
                    if (company.includes('LG')) compSelect.value = 'LG Plast';
                    else if (company.includes('Tagoneswa') || company.includes('TG')) compSelect.value = 'Tagoneswa Hardware';
                    else if (company.includes('Kreckle')) compSelect.value = 'Kreckle Foods';
                    else compSelect.value = company;
                } else if (window.selectedFleetCompany && window.selectedFleetCompany !== 'ALL') {
                    compSelect.value = window.selectedFleetCompany;
                }
            }

            const roleSelect = document.getElementById('modal-salesrep-role');
            if (roleSelect && role) {
                roleSelect.value = role;
            }

            const fb = document.getElementById('modal-salesrep-feedback');
            if (fb) fb.classList.add('hidden');
            modal.classList.remove('hidden');
            syncBodyScrollLock();
        }

        function closeAddSalesRepModal() {
            const modal = document.getElementById('addSalesRepModal');
            if (modal) modal.classList.add('hidden');
            syncBodyScrollLock();
        }

        async function submitSaveSalesRep() {
            const empId = document.getElementById('modal-salesrep-id').value;
            const name = (document.getElementById('modal-salesrep-name').value || '').trim();
            const phone = (document.getElementById('modal-salesrep-phone').value || '').trim();
            const email = (document.getElementById('modal-salesrep-email').value || '').trim();
            const active = document.getElementById('modal-salesrep-active').checked;
            const company = document.getElementById('modal-salesrep-company')?.value || 'LG Plast';
            const role = document.getElementById('modal-salesrep-role')?.value || 'SALES_REP';
            const btn = document.getElementById('modal-submit-salesrep-btn');
            const fb = document.getElementById('modal-salesrep-feedback');

            if (!name || !phone) {
                alert('Please enter sales representative name and WhatsApp phone number.');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = 'Saving Sales Rep...';

            try {
                const res = await fetch('/api/v2/fleet/sales-reps/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        employee_id: empId ? parseInt(empId) : null,
                        full_name: name,
                        phone: phone,
                        email: email,
                        company: company,
                        role: role,
                        active: active
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Sales Rep ${name} (${company}) saved successfully!`);
                    closeAddSalesRepModal();
                    await fetchDashboard();
                } else {
                    if (fb) {
                        fb.textContent = data.detail || 'Failed to save sales representative';
                        fb.className = 'text-xs font-bold text-rose-600 block';
                    } else {
                        alert(data.detail || 'Failed to save sales representative');
                    }
                }
            } catch (err) {
                alert('Network error saving sales rep: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Save Sales Rep';
            }
        }

        async function deleteSalesRep(phone, name) {
            if (!confirm(`Are you sure you want to remove sales representative ${name} (+${phone})?`)) return;
            try {
                const res = await fetch('/api/fleet/salespersons/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone: phone })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`Sales representative ${name} removed.`);
                    await fetchDashboard();
                } else {
                    alert(data.detail || 'Failed to remove sales representative');
                }
            } catch (err) {
                alert('Network error removing sales rep: ' + err.message);
            }
        }
        window.deleteSalesRep = deleteSalesRep;

        // Initialize dashboard
        setupModalInteractions();
        switchDomain(initialDefaultTab);
        fetchDashboard();
        setInterval(() => {
            if (!document.hidden) {
                fetchDashboard();
            }
        }, 15000);
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                fetchDashboard();
            }
        });

        // Auto-apply company filter if the logged-in user has a company (e.g. named Sales Admin)
        if (window.currentUserCompany && window.currentUserCompany.trim() !== '') {
            // Apply after first data loads (1.5s grace to allow fetchDashboard to complete)
            setTimeout(() => {
                if (typeof switchFleetCompany === 'function') {
                    switchFleetCompany(window.currentUserCompany);
                }
            }, 1500);
        }
