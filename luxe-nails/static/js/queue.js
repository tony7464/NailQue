        let servicesMenu = [];
        let commissionRate = 0.6;
        let salonSettings = {
            salonName: "NailQue",
            tagline: "NAIL SPA",
            idleLockMinutes: 5,
            bonusHours: { start: "08:00", end: "09:30" },
            services: []
        };
        let techs = {};
        let waitingQueue = [];
        let appointments = [];
        let currentFinishingTech = null;
        let finishCustomAddons = [];
        let nextCustomerId = 1;
        let bonusOrder = [];
        let lastReceipt = null;
        let managerMustChangePin = false;
        let lastManagerActivityAt = Date.now();
        let todayServiceCount = 0;

        const queueStateKey = "mvQueueState";
        const serviceRecordsKey = "mvServiceRecords";
        const bonusSettingsKey = "mvBonusSettings";
        const bonusClockInsKey = "mvBonusClockIns";
        const managerActivityLogKey = "mvManagerActivityLog";
        const queueThemeKey = "mvQueueTheme";

        let bonusSettings = { start: "08:00", end: "09:30" };
        let bonusClockIns = {};
        let pendingRemoveTechName = null;
        let toastTimeoutId = null;
        let managerActivityLog = [];
        let lastRemovedTechSnapshot = null;
        let bonusCycleQueue = [];
        let bonusCycleServed = [];
        let latestUpdateStatus = null;
        let mobileAccessUrl = "";
        let currentManagerUsername = "";
        let currentManagerFullName = "";
        let managerAuthToken = "";
        let pendingUpdateAfterLogin = false;
        let credentialsConfiguredOnServer = false;
        let queueListAnimationFrame = 0;
        let hasTechAssignmentSnapshot = false;
        let techAssignmentSnapshot = {};
        const soundFx = {
            startup: "/assets/sounds/startup_fx.mp3",
            click: "/assets/sounds/click_fx.mp3",
            customer: "/assets/sounds/startup_fx.mp3",
        };
        const soundPlayers = {};

        function normalizeIdentifier(value) {
            return String(value || "").trim().toLowerCase();
        }

        function formatTechIdentity(rawName) {
            const parts = String(rawName || "")
                .trim()
                .split(/\s+/)
                .filter(Boolean)
                .map((part) => part.replace(/[^a-zA-Z'-]/g, ""));
            if (parts.length < 2) return null;
            const first = parts[0];
            const last = parts[parts.length - 1];
            if (!first || !last) return null;
            const firstName = first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
            const lastInitial = last.charAt(0).toUpperCase();
            if (!/[A-Z]/.test(lastInitial)) return null;
            return {
                techName: `${firstName} ${lastInitial}`,
                identifier: `${firstName.toLowerCase()}${lastInitial.toLowerCase()}`
            };
        }

        function playSoundEffect(kind, volumeOverride) {
            const src = soundFx[kind];
            if (!src) return Promise.resolve(false);
            const player = soundPlayers[kind] || new Audio(src);
            if (!soundPlayers[kind]) {
                player.preload = "auto";
                soundPlayers[kind] = player;
            }
            player.volume = typeof volumeOverride === "number" ? volumeOverride : 0.6;
            player.currentTime = 0;
            const playResult = player.play();
            if (playResult && typeof playResult.then === "function") {
                return playResult.then(() => true).catch(() => false);
            }
            return Promise.resolve(true);
        }

        function playCustomerAssignedChime() {
            // Prefer bundled chime and replay softly for audibility in salon noise.
            playSoundEffect("customer", 0.82).then((played) => {
                if (played) return;
                synthesizeCustomerChime();
            });
            setTimeout(() => {
                playSoundEffect("customer", 0.62);
            }, 230);
        }

        function synthesizeCustomerChime() {
            try {
                const Context = window.AudioContext || window.webkitAudioContext;
                if (!Context) return;
                const audioCtx = new Context();
                const now = audioCtx.currentTime;
                const notes = [392.0, 523.25, 659.25];
                notes.forEach((frequency, index) => {
                    const osc = audioCtx.createOscillator();
                    const gain = audioCtx.createGain();
                    osc.type = index === notes.length - 1 ? "triangle" : "sine";
                    osc.frequency.setValueAtTime(frequency, now + index * 0.15);
                    gain.gain.setValueAtTime(0.0001, now + index * 0.15);
                    gain.gain.exponentialRampToValueAtTime(0.065, now + index * 0.15 + 0.03);
                    gain.gain.exponentialRampToValueAtTime(0.0001, now + index * 0.15 + 0.34);
                    osc.connect(gain);
                    gain.connect(audioCtx.destination);
                    osc.start(now + index * 0.15);
                    osc.stop(now + index * 0.15 + 0.36);
                });
                setTimeout(() => {
                    audioCtx.close().catch(() => {});
                }, 760);
            } catch (error) {
                // Ignore sound failures; visuals still indicate assignment.
            }
        }

        function detectNewCustomerAssignments() {
            const nextSnapshot = {};
            let shouldChime = false;
            Object.entries(techs).forEach(([name, t]) => {
                const currentCustomer = (t && t.status === "Busy" && t.current) ? String(t.current) : "";
                nextSnapshot[name] = currentCustomer;
                if (!hasTechAssignmentSnapshot) return;
                const previousCustomer = String(techAssignmentSnapshot[name] || "");
                if (currentCustomer && currentCustomer !== previousCustomer) {
                    shouldChime = true;
                }
            });
            techAssignmentSnapshot = nextSnapshot;
            if (!hasTechAssignmentSnapshot) {
                hasTechAssignmentSnapshot = true;
                return;
            }
            if (shouldChime) {
                playCustomerAssignedChime();
            }
        }

        function setupSoundEffects() {
            Object.keys(soundFx).forEach((kind) => {
                const player = new Audio(soundFx[kind]);
                player.preload = "auto";
                soundPlayers[kind] = player;
            });

            document.addEventListener("click", (event) => {
                const clickable = event.target.closest("button, [role='button'], .btn, .btn-small, .add-btn, .nav-pill-btn");
                if (!clickable) return;
                playSoundEffect("click");
            }, true);
        }

        function managerHeaders(extra) {
            const headers = Object.assign({}, extra || {});
            if (managerAuthToken) {
                headers.Authorization = "Bearer " + managerAuthToken;
            }
            return headers;
        }

        function credentialMetaFromLegacy(raw) {
            const meta = {};
            Object.entries(raw || {}).forEach(([name, cred]) => {
                if (!cred || typeof cred !== "object") return;
                meta[name] = {
                    identifier: String(cred.identifier || "").trim(),
                    mustChangePassword: Boolean(cred.mustChangePassword)
                };
            });
            return meta;
        }

        function getCredentialMeta() {
            return JSON.parse(localStorage.getItem("nailTechCredentialMeta") || "{}");
        }

        function saveCredentialMeta(meta) {
            localStorage.setItem("nailTechCredentialMeta", JSON.stringify(meta || {}));
        }

        function getLegacyCredentialsForMigration() {
            return JSON.parse(localStorage.getItem("nailTechCredentials") || "{}");
        }

        function clearLegacyPasswordsFromBrowser() {
            const legacy = getLegacyCredentialsForMigration();
            if (legacy && Object.keys(legacy).length) {
                saveCredentialMeta(credentialMetaFromLegacy(legacy));
            }
            localStorage.removeItem("nailTechCredentials");
        }

        function nowMinutes() {
            const d = new Date();
            return d.getHours() * 60 + d.getMinutes();
        }

        function hhmmToMinutes(value) {
            if (!value || !value.includes(":")) return 0;
            const [h, m] = value.split(":").map((v) => parseInt(v, 10));
            return (h * 60) + m;
        }

        function isInBonusWindow() {
            const start = hhmmToMinutes(bonusSettings.start);
            const end = hhmmToMinutes(bonusSettings.end);
            const current = nowMinutes();
            return current >= start && current <= end;
        }

        function rebuildBonusOrder() {
            if (!isInBonusWindow()) {
                bonusOrder = [];
                return;
            }
            bonusOrder = Object.entries(bonusClockIns)
                .filter(([name]) => techs[name] && techs[name].status === "Available")
                .sort((a, b) => a[1] - b[1])
                .map(([name]) => name);
        }

        function syncBonusCycleQueue() {
            if (!isInBonusWindow()) {
                bonusCycleQueue = [];
                bonusCycleServed = [];
                return;
            }
            const eligible = Object.entries(bonusClockIns)
                .filter(([name]) => techs[name] && techs[name].status === "Available")
                .sort((a, b) => a[1] - b[1])
                .map(([name]) => name);

            // Keep only still-eligible names in current queue.
            bonusCycleQueue = bonusCycleQueue.filter((name) => eligible.includes(name));
            bonusCycleServed = bonusCycleServed.filter((name) => techs[name]);

            // Add newly eligible names that have not had their bonus turn yet this cycle.
            eligible.forEach((name) => {
                if (!bonusCycleQueue.includes(name) && !bonusCycleServed.includes(name)) {
                    bonusCycleQueue.push(name);
                }
            });
        }

        function markBonusTurnUsed(techName) {
            if (!isInBonusWindow()) return;
            bonusCycleQueue = bonusCycleQueue.filter((name) => name !== techName);
            if (!bonusCycleServed.includes(techName)) {
                bonusCycleServed.push(techName);
            }
        }

        function getNextAvailableTechForAssignment() {
            syncBonusCycleQueue();
            if (bonusCycleQueue.length > 0) {
                return bonusCycleQueue[0];
            }
            const available = Object.keys(techs)
                .filter((name) => techs[name].status === "Available")
                .sort((a, b) => {
                    const aTime = bonusClockIns[a] || Number.MAX_SAFE_INTEGER;
                    const bTime = bonusClockIns[b] || Number.MAX_SAFE_INTEGER;
                    return aTime - bTime;
                });
            return available[0] || null;
        }

        function getBonusOrderPreview() {
            syncBonusCycleQueue();
            return bonusCycleQueue.slice();
        }

        function getTechDisplayOrder() {
            const availablePriority = [];
            const busy = [];
            const scheduled = [];
            const onBreak = [];
            const offline = [];

            const bonusPending = getBonusOrderPreview();
            const availableAll = Object.keys(techs)
                .filter((name) => techs[name].status === "Available")
                .sort((a, b) => {
                    const aTime = bonusClockIns[a] || Number.MAX_SAFE_INTEGER;
                    const bTime = bonusClockIns[b] || Number.MAX_SAFE_INTEGER;
                    return aTime - bTime;
                });

            bonusPending.forEach((name) => {
                if (techs[name] && techs[name].status === "Available") availablePriority.push(name);
            });
            availableAll.forEach((name) => {
                if (!availablePriority.includes(name)) availablePriority.push(name);
            });

            Object.keys(techs).forEach((name) => {
                const status = techs[name].status;
                if (status === "Busy") busy.push(name);
                else if (status === "On Break") onBreak.push(name);
                else if (status === "Scheduled Appointment") scheduled.push(name);
                else if (status === "Offline") offline.push(name);
            });

            busy.sort((a, b) => (techs[a].startTime || Number.MAX_SAFE_INTEGER) - (techs[b].startTime || Number.MAX_SAFE_INTEGER));
            return [...availablePriority, ...busy, ...onBreak, ...scheduled, ...offline];
        }

        function getQueueAnalytics() {
            return {
                waiting: waitingQueue.length,
                completedToday: todayServiceCount
            };
        }

        function applySalonSettings(settings) {
            if (!settings || typeof settings !== "object") return;
            salonSettings = Object.assign({}, salonSettings, settings);
            if (Array.isArray(settings.services) && settings.services.length) {
                servicesMenu = settings.services;
            }
            if (typeof settings.commissionRate === "number") {
                commissionRate = settings.commissionRate;
            }
            if (settings.bonusHours && settings.bonusHours.start && settings.bonusHours.end) {
                bonusSettings = settings.bonusHours;
            }
            const nameEl = document.getElementById("salonHeaderName");
            const tagEl = document.getElementById("salonTagline");
            if (nameEl) nameEl.textContent = salonSettings.salonName || "NailQue";
            if (tagEl) tagEl.textContent = salonSettings.tagline || "NAIL SPA";
            const shareLabel = document.getElementById("employeeShareLabel");
            if (shareLabel) shareLabel.textContent = `Employee Share (${Math.round(commissionRate * 100)}%)`;
            const nameInput = document.getElementById("salonNameInput");
            const tagInput = document.getElementById("salonTaglineInput");
            const commissionInput = document.getElementById("commissionRateInput");
            const idleInput = document.getElementById("idleLockInput");
            if (nameInput) nameInput.value = salonSettings.salonName || "";
            if (tagInput) tagInput.value = salonSettings.tagline || "";
            if (commissionInput) commissionInput.value = String(Math.round(commissionRate * 100));
            if (idleInput) idleInput.value = String(salonSettings.idleLockMinutes || 5);
            renderSalonServicesEditor();
        }

        async function queueMutate(action, payload) {
            const { ok, data } = await apiRequest("/api/queue/action", {
                method: "POST",
                token: managerAuthToken,
                body: Object.assign({ action }, payload || {})
            });
            if (!ok || !data.ok) {
                throw new Error((data && data.error) || "Queue update failed.");
            }
            if (data.state) applySharedStateFromServer(data.state);
            if (data.receipt) {
                lastReceipt = data.receipt;
            }
            return data;
        }

        async function syncSharedStateToServer() {
            return false;
        }

        function applySharedStateFromServer(state) {
            if (!state || typeof state !== "object") return;
            if (!state.techs || !Array.isArray(state.waitingQueue)) return;
            techs = state.techs;
            waitingQueue = state.waitingQueue;
            appointments = Array.isArray(state.appointments) ? state.appointments : [];
            if (Number.isInteger(state.nextCustomerId)) nextCustomerId = state.nextCustomerId;
            if (state.bonusClockIns && typeof state.bonusClockIns === "object") bonusClockIns = state.bonusClockIns;
            credentialsConfiguredOnServer = Boolean(state.credentialsConfigured);
            if (state.credentialMeta && typeof state.credentialMeta === "object") {
                saveCredentialMeta(state.credentialMeta);
            }
            if (credentialsConfiguredOnServer) {
                localStorage.removeItem("nailTechCredentials");
            }
            localStorage.setItem(queueStateKey, JSON.stringify({ techs, waitingQueue, nextCustomerId, appointments }));
            renderTechBoard();
            renderQueue();
            renderAppointments();
            renderManagerTechList();
        }

        async function fetchSharedStateFromServer() {
            try {
                const response = await fetch("/api/shared/state");
                const data = await response.json();
                if (!response.ok || !data.ok || !data.state) return false;
                applySharedStateFromServer(data.state);
                if (data.salon) applySalonSettings(data.salon);
                if (Number.isInteger(data.completedToday)) todayServiceCount = data.completedToday;
                return true;
            } catch (error) {
                return false;
            }
        }

        function formatAppointmentLabel(timestampMs) {
            if (!timestampMs) return "";
            return new Date(timestampMs).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
        }

        function getAvailableTechPriorityList() {
            syncBonusCycleQueue();
            const ordered = [];
            bonusCycleQueue.forEach((name) => {
                if (techs[name] && techs[name].status === "Available" && !ordered.includes(name)) {
                    ordered.push(name);
                }
            });
            Object.keys(techs)
                .filter((name) => techs[name].status === "Available" && !ordered.includes(name))
                .sort((a, b) => {
                    const aTime = bonusClockIns[a] || Number.MAX_SAFE_INTEGER;
                    const bTime = bonusClockIns[b] || Number.MAX_SAFE_INTEGER;
                    return aTime - bTime;
                })
                .forEach((name) => ordered.push(name));
            return ordered;
        }

        function findAssignableCustomerIndex(techName) {
            const now = Date.now();
            return waitingQueue.findIndex((customer) => {
                const appointmentReady = !customer.appointmentTime || customer.appointmentTime <= now;
                const matchesRequestedTech = !customer.requestedTech || customer.requestedTech === techName;
                return appointmentReady && matchesRequestedTech;
            });
        }

        function autoAssign() {
            renderQueue();
            renderTechBoard();
        }

        function renderQueue() {
            const queue = document.getElementById("queueList");
            const header = document.getElementById("queueHeaderText");
            header.textContent = `WAITING CUSTOMERS (${waitingQueue.length})`;
            if (waitingQueue.length === 0) {
                queue.innerHTML = `<div style="color:#a58f6b; text-align:center; padding:14px;">No customers waiting</div>`;
                return;
            }
            const previousTops = new Map();
            queue.querySelectorAll(".queue-item[data-customer-id]").forEach((item) => {
                previousTops.set(item.dataset.customerId, item.getBoundingClientRect().top);
            });

            queue.innerHTML = "";
            const fragment = document.createDocumentFragment();
            waitingQueue.forEach((customer, idx) => {
                const waitMins = Math.max(0, Math.round((Date.now() - customer.arrival) / 60000));
                const appointmentText = customer.appointmentTime ? ` • ${formatAppointmentLabel(customer.appointmentTime)}` : "";
                const requestedTechText = customer.requestedTech ? ` • Request: ${escapeHtml(customer.requestedTech)}` : "";
                const detailText = `${appointmentText}${requestedTechText}`;
                const appointmentBadge = customer.appointmentTime ? `<span class="appt-badge">APPT</span>` : "";
                const row = document.createElement("div");
                row.className = "queue-item";
                row.dataset.customerId = String(customer.id ?? `${customer.name}-${customer.arrival}-${idx}`);
                row.innerHTML = `
                    <div><strong>#${idx + 1}</strong> ${customer.name}${appointmentBadge}${detailText ? `<div style="font-size:12px;color:#a58f6b;margin-top:4px;">${detailText}</div>` : ""}</div>
                    <div style="color:#d4af77;display:flex;align-items:center;gap:8px;">
                        <span>${waitMins} min</span>
                        <div class="queue-item-actions">
                            <button type="button" class="btn-small" onclick="skipWaitingCustomer(${Number(customer.id)})">Skip</button>
                            <button type="button" class="btn-small" style="background:#6b3030;color:#f5f0e8;" onclick="removeWaitingCustomer(${Number(customer.id)})">Remove</button>
                        </div>
                    </div>
                `;
                fragment.appendChild(row);
            });
            queue.appendChild(fragment);

            if (queueListAnimationFrame) {
                cancelAnimationFrame(queueListAnimationFrame);
            }
            queueListAnimationFrame = requestAnimationFrame(() => {
                queue.querySelectorAll(".queue-item[data-customer-id]").forEach((item) => {
                    const id = item.dataset.customerId;
                    const beforeTop = previousTops.get(id);
                    if (beforeTop === undefined) return;
                    const afterTop = item.getBoundingClientRect().top;
                    const deltaY = beforeTop - afterTop;
                    if (Math.abs(deltaY) < 1) return;
                    item.style.transform = `translateY(${deltaY}px)`;
                    item.classList.add("queue-item-moving");
                    requestAnimationFrame(() => {
                        item.style.transform = "translateY(0)";
                    });
                    setTimeout(() => {
                        item.classList.remove("queue-item-moving");
                    }, 380);
                });
            });
        }

        function renderAppointments() {
            const list = document.getElementById("appointmentList");
            if (!list) return;
            const booked = (appointments || []).filter((item) => item && item.status === "booked");
            if (!booked.length) {
                list.innerHTML = `<div style="color:#a58f6b; text-align:center; padding:14px;">No booked appointments</div>`;
                return;
            }
            booked.sort((a, b) => (a.appointmentTime || 0) - (b.appointmentTime || 0));
            list.innerHTML = booked.map((item) => {
                const when = formatAppointmentLabel(item.appointmentTime);
                const tech = item.requestedTech ? ` • ${escapeHtml(item.requestedTech)}` : "";
                return `<div class="queue-item">
                    <div><strong>${escapeHtml(item.name || "Guest")}</strong><div style="font-size:12px;color:#a58f6b;margin-top:4px;">${when}${tech}</div></div>
                    <div class="queue-item-actions">
                        <button type="button" class="btn-small" style="background:#2d5b4a;color:#f5f0e8;" onclick="arriveAppointment(${Number(item.id)})">Arrived</button>
                        <button type="button" class="btn-small" style="background:#6b3030;color:#f5f0e8;" onclick="cancelAppointment(${Number(item.id)})">Cancel</button>
                    </div>
                </div>`;
            }).join("");
        }

        function statusBadgeForTech(tech) {
            if (tech.status === "Scheduled Appointment") {
                return `<div class="status scheduled">SCHEDULED APPOINTMENT</div>`;
            }
            if (tech.status === "On Break") {
                return `<div class="status on-break">ON BREAK</div>`;
            }
            if (tech.status === "Available") return `<div class="status available">AVAILABLE</div>`;
            if (tech.status === "Busy") {
                const mins = tech.startTime ? Math.max(0, Math.round((Date.now() - tech.startTime) / 60000)) : 0;
                return `<div class="status busy">BUSY ${tech.current ? `<div style="font-size:18px; margin-top:6px;">${tech.current} • ${mins}m</div>` : ""}</div>`;
            }
            return `<div class="status offline">OFFLINE</div>`;
        }

        function renderTechBoard() {
            detectNewCustomerAssignments();
            const board = document.getElementById("techBoard");
            const metrics = getQueueAnalytics();
            const bonusPreview = getBonusOrderPreview();
            board.innerHTML = `
                <div style="font-size:26px; color:#d4af77; margin-bottom:6px; text-align:center;">LIVE TECH STATUS</div>
                <div style="text-align:center; color:#a58f6b; font-size:13px; margin-bottom:8px;">★ Bonus turn pending</div>
                <div class="summary-grid">
                    <div class="summary-card"><div class="summary-label">Waiting</div><div class="summary-value">${metrics.waiting}</div></div>
                    <div class="summary-card"><div class="summary-label">Completed Today</div><div class="summary-value">${metrics.completedToday}</div></div>
                </div>
            `;
            const orderedNames = getTechDisplayOrder();
            orderedNames.forEach((name) => {
                const t = techs[name];
                const hasBonusTurn = bonusPreview.includes(name);
                board.innerHTML += `
                <div class="tech-panel">
                    <div><div class="tech-name">${hasBonusTurn ? '<span class="bonus-star">★</span>' : ""}${name}</div></div>
                    ${statusBadgeForTech(t)}
                    <div class="buttons">
                        <button class="btn" onclick="signInTech('${name}')" style="background:#d4af77;color:#1a1208;">READY</button>
                        <button class="btn" onclick="unreadyTech('${name}')" style="background:#4a3f35;color:#f5f0e8;">UNREADY</button>
                        <button class="btn" onclick="toggleTechBreak('${name}')" style="background:#7a5a3a;color:#f5f0e8;">${t.status === "On Break" ? "END BREAK" : "BREAK"}</button>
                        <button class="btn" onclick="skipNextForTech('${name}')" style="background:#3f566f;color:#f5f0e8;">SKIP NEXT</button>
                        <button class="btn btn-finish" onclick="finishTech('${name}')" style="background:#c48b6f;color:#fff;">FINISH CUSTOMER</button>
                    </div>
                </div>`;
            });
        }

        function renderManagerTechList() {
            const el = document.getElementById("managerTechList");
            const names = Object.keys(techs);
            if (names.length === 0) {
                el.innerHTML = `<div style="color:#a58f6b;">No techs found.</div>`;
                renderManagerReassignControls();
                return;
            }
            el.innerHTML = names.map((name) => {
                const encodedName = encodeURIComponent(name);
                return `
                <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px;background:#2a221b;padding:10px;border-radius:12px;">
                    <div style="flex:1;min-width:100px;color:#f5f0e8;font-weight:600;">${escapeHtml(name)}</div>
                    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
                        <select class="select-input tech-status-select" data-tech="${encodedName}" style="margin-bottom:0;max-width:200px;">
                            <option value="Offline" ${techs[name].status === "Offline" ? "selected" : ""}>Offline</option>
                            <option value="Available" ${techs[name].status === "Available" ? "selected" : ""}>Available</option>
                            <option value="Busy" ${techs[name].status === "Busy" ? "selected" : ""}>Busy</option>
                            <option value="On Break" ${techs[name].status === "On Break" ? "selected" : ""}>On Break</option>
                            <option value="Scheduled Appointment" ${techs[name].status === "Scheduled Appointment" ? "selected" : ""}>Scheduled Appointment</option>
                        </select>
                        <button type="button" class="btn-small tech-reset-btn" data-tech="${encodedName}" style="background:#3d2a1f;color:#d4af77;">Reset password</button>
                        <button type="button" class="btn-small tech-remove-btn" data-tech="${encodedName}" style="background:#6b3030;color:#f5f0e8;">Remove</button>
                    </div>
                </div>`;
            }).join("");
            renderManagerReassignControls();
        }

        function renderManagerReassignControls() {
            const fromSelect = document.getElementById("reassignFromTechSelect");
            const toSelect = document.getElementById("reassignToTechSelect");
            if (!fromSelect || !toSelect) return;
            const names = Object.keys(techs);
            const busyWithCustomer = names.filter((name) => techs[name] && techs[name].status === "Busy" && techs[name].current);
            const eligibleTargets = names.filter((name) => !techs[name] || techs[name].status !== "Busy");
            fromSelect.innerHTML = busyWithCustomer.length
                ? busyWithCustomer.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)} (${escapeHtml(techs[name].current)})</option>`).join("")
                : `<option value="">No active customers to move</option>`;
            toSelect.innerHTML = eligibleTargets.length
                ? eligibleTargets.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)} (${escapeHtml(techs[name].status || "Offline")})</option>`).join("")
                : `<option value="">No destination tech available</option>`;
        }

        async function performManagerReassign() {
            const fromName = document.getElementById("reassignFromTechSelect").value;
            const toName = document.getElementById("reassignToTechSelect").value;
            if (!fromName || !toName) {
                showManagerMessage("Select both source and destination tech.", true);
                return;
            }
            if (fromName === toName) {
                showManagerMessage("Source and destination must be different techs.", true);
                return;
            }
            try {
                await queueMutate("reassign", { fromTech: fromName, toTech: toName });
                showManagerMessage(`Moved customer from ${fromName} to ${toName}.`);
                showActionToast(`Customer moved: ${fromName} -> ${toName}.`, false);
                addManagerActivity(`Reassigned customer from ${fromName} to ${toName}.`, "success");
            } catch (error) {
                showManagerMessage(error.message, true);
                showActionToast(error.message, true);
            }
        }

        function escapeHtml(value) {
            return String(value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }

        function getTechNameFromDataset(element) {
            if (!element || !element.dataset || !element.dataset.tech) return "";
            try {
                return decodeURIComponent(element.dataset.tech);
            } catch (error) {
                return "";
            }
        }

        function onManagerTechListClick(event) {
            const resetButton = event.target.closest(".tech-reset-btn");
            if (resetButton) {
                const techName = getTechNameFromDataset(resetButton);
                if (techName) resetTechAccountPassword(techName);
                return;
            }
            const removeButton = event.target.closest(".tech-remove-btn");
            if (removeButton) {
                const techName = getTechNameFromDataset(removeButton);
                if (techName) openRemoveTechConfirm(techName);
            }
        }

        function onManagerTechListChange(event) {
            const select = event.target.closest(".tech-status-select");
            if (!select) return;
            const techName = getTechNameFromDataset(select);
            if (techName) setTechStatusOverride(techName, select.value);
        }

        function showManagerMessage(msg, isError) {
            const el = document.getElementById("managerMessage");
            el.style.color = isError ? "#ff9b9b" : "#d4af77";
            el.textContent = msg;
        }

        function showActionToast(message, isError) {
            const toast = document.getElementById("actionToast");
            if (!toast) return;
            toast.textContent = message;
            toast.classList.toggle("error", !!isError);
            toast.style.display = "block";
            if (toastTimeoutId) {
                clearTimeout(toastTimeoutId);
            }
            toastTimeoutId = setTimeout(() => {
                toast.style.display = "none";
            }, 2800);
        }

        function addManagerActivity(message, level) {
            const actor = currentManagerFullName || currentManagerUsername || "Manager";
            const entry = {
                message,
                actor,
                level: level || "info",
                timestamp: new Date().toISOString()
            };
            managerActivityLog.unshift(entry);
            managerActivityLog = managerActivityLog.slice(0, 80);
            localStorage.setItem(managerActivityLogKey, JSON.stringify(managerActivityLog));
            renderManagerActivityLog();
            persistManagerActivityEntry(entry);
        }

        async function fetchManagerActivityLog() {
            if (!managerAuthToken) return false;
            try {
                const { ok, data } = await apiRequest("/api/manager/activity", { token: managerAuthToken });
                if (!ok || !data.ok) throw new Error(data.error || "Could not load manager activity log.");
                const records = Array.isArray(data.records) ? data.records : [];
                managerActivityLog = records.slice().reverse().slice(0, 80);
                localStorage.setItem(managerActivityLogKey, JSON.stringify(managerActivityLog));
                renderManagerActivityLog();
                return true;
            } catch (error) {
                return false;
            }
        }

        async function persistManagerActivityEntry(entry) {
            if (!managerAuthToken) return;
            try {
                await apiRequest("/api/manager/activity", { method: "POST", token: managerAuthToken, body: entry });
            } catch (error) {
                // Local log remains as fallback if server write fails.
            }
        }

        function formatUpdateTimestamp(unixSeconds) {
            if (!unixSeconds) return "Never";
            return new Date(unixSeconds * 1000).toLocaleString();
        }

        function renderUpdateStatusPanel(status) {
            const panel = document.getElementById("updateStatusPanel");
            if (!panel) return;
            if (!status) {
                panel.innerHTML = `<div style="color:#a58f6b;">Update status unavailable.</div>`;
                return;
            }
            const enabled = !!status.enabled;
            const available = !!status.available;
            const downloaded = !!(status.package_ready || status.downloaded_path);
            const checking = !!status.checking;
            const error = status.last_error ? escapeHtml(status.last_error) : "";
            const latest = escapeHtml(status.latest_version || "unknown");
            const current = escapeHtml(status.current_version || "unknown");
            const downloadedPath = downloaded ? "Ready to install" : "";
            const checkedAt = formatUpdateTimestamp(status.last_checked);
            panel.innerHTML = `
                <div style="color:#f5f0e8;"><strong>Current:</strong> ${current}</div>
                <div style="color:#f5f0e8;"><strong>Latest:</strong> ${latest}</div>
                <div style="color:${enabled ? "#d4af77" : "#ffb3b3"};"><strong>Updater:</strong> ${enabled ? "Enabled" : "Disabled"}</div>
                <div style="color:${available ? "#d4af77" : "#a58f6b"};"><strong>Status:</strong> ${checking ? "Checking..." : (available ? "Update available" : "Up to date")}</div>
                <div style="color:${downloaded ? "#d4af77" : "#a58f6b"};"><strong>Package:</strong> ${downloaded ? "Downloaded" : "Not downloaded yet"}</div>
                ${downloaded ? `<div style="color:#a58f6b;font-size:12px;"><strong>Package:</strong> ${downloadedPath}</div>` : ""}
                <div style="color:#a58f6b;font-size:12px;"><strong>Last check:</strong> ${escapeHtml(checkedAt)}</div>
                ${error ? `<div style="color:#ffd9d9;font-size:12px;"><strong>Error:</strong> ${error}</div>` : ""}
            `;
            refreshQuickUpdateButton(status);
        }

        function refreshQuickUpdateButton(status) {
            const btn = document.getElementById("quickUpdateBtn");
            if (!btn) return;
            const ready = !!(status && status.available && (status.package_ready || status.downloaded_path));
            btn.classList.toggle("update-ready", ready);
            btn.textContent = ready ? "UPDATE READY" : "CHECK UPDATES";
        }

        async function fetchUpdateStatus(showErrors) {
            if (!managerAuthToken) return;
            try {
                const { ok, data } = await apiRequest("/api/update/status", { token: managerAuthToken });
                if (!ok) {
                    throw new Error(data.error || "Could not load update status.");
                }
                latestUpdateStatus = data;
                renderUpdateStatusPanel(data);
                if (data.available && (data.package_ready || data.downloaded_path)) {
                    showActionToast(`Update ${data.latest_version} is ready to install.`, false);
                }
            } catch (error) {
                if (showErrors) {
                    showActionToast(error.message || "Update status request failed.", true);
                }
            }
        }

        async function checkForUpdatesNow() {
            if (!managerAuthToken) {
                pendingUpdateAfterLogin = true;
                openManagerAccess();
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/update/check", { method: "POST", token: managerAuthToken });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not start update check.");
                }
                showActionToast("Checking for updates...", false);
                setTimeout(() => fetchUpdateStatus(false), 1200);
            } catch (error) {
                showActionToast(error.message || "Update check failed.", true);
            }
        }

        async function runOneTapUpdateFlow() {
            if (!managerAuthToken) {
                pendingUpdateAfterLogin = true;
                openManagerAccess();
                showActionToast("Sign in as a manager to install updates.", false);
                return;
            }
            try {
                showActionToast("Checking for updates...", false);
                const { ok, data: checkData } = await apiRequest("/api/update/check-sync", { method: "POST", token: managerAuthToken });
                if (!ok || !checkData.ok) {
                    throw new Error(checkData.error || "Could not check updates.");
                }
                const status = checkData.status || {};
                latestUpdateStatus = status;
                renderUpdateStatusPanel(status);
                if (!status.available) {
                    showActionToast("App is already up to date.", false);
                    return;
                }
                if (!(status.package_ready || status.downloaded_path)) {
                    showActionToast("Update found but package is not downloaded yet. Try again in a moment.", true);
                    return;
                }
                const proceed = confirm(`Update ${status.latest_version || "available"} is ready. Install now and restart app?`);
                if (!proceed) return;
                const { ok: installOk, data: installData } = await apiRequest("/api/update/install", { method: "POST", token: managerAuthToken });
                if (!installOk || !installData.ok) {
                    throw new Error(installData.error || "Install failed.");
                }
                showActionToast(installData.message || "Installing update and restarting app...", false);
                addManagerActivity(`Installed app update ${status.latest_version || ""} from quick update action.`, "success");
            } catch (error) {
                showActionToast(error.message || "Update flow failed.", true);
            }
        }

        async function installLatestUpdate() {
            if (!managerAuthToken) {
                openManagerAccess();
                return;
            }
            try {
                const proceed = confirm("Install latest downloaded update now? macOS may ask for admin password.");
                if (!proceed) return;
                const { ok, data } = await apiRequest("/api/update/install", { method: "POST", token: managerAuthToken });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Install failed.");
                }
                showActionToast(data.message || "Update installed.", false);
                addManagerActivity(`Installed app update ${latestUpdateStatus && latestUpdateStatus.latest_version ? latestUpdateStatus.latest_version : ""}.`, "success");
            } catch (error) {
                showActionToast(error.message || "Could not install update.", true);
                addManagerActivity("Failed app update install attempt.", "error");
            }
        }

        function renderMobileTechSessions(items) {
            const panel = document.getElementById("mobileTechSessionsPanel");
            if (!panel) return;
            const sessions = Array.isArray(items) ? items : [];
            if (!sessions.length) {
                panel.innerHTML = `<div style="color:#a58f6b;">No active mobile sessions.</div>`;
                return;
            }
            panel.innerHTML = sessions
                .map((session) => {
                    const tech = escapeHtml(session.tech || "Tech");
                    const ip = escapeHtml(session.ip || "unknown");
                    const minutes = Math.max(1, Math.ceil((Number(session.expiresInSeconds) || 0) / 60));
                    return `<div class="activity-row"><span style="color:#f5f0e8;">${tech} • ${ip}</span><span class="activity-time">${minutes}m</span></div>`;
                })
                .join("");
        }

        async function fetchMobileTechSessions() {
            if (!managerAuthToken) return;
            try {
                const { ok, data } = await apiRequest("/api/mobile/active-techs", { token: managerAuthToken });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not load mobile sessions.");
                }
                renderMobileTechSessions(data.activeTechs || []);
            } catch (error) {
                renderMobileTechSessions([]);
            }
        }

        function renderServiceHistory(records) {
            const panel = document.getElementById("serviceHistoryPanel");
            if (!panel) return;
            const items = Array.isArray(records) ? records.slice().reverse().slice(0, 20) : [];
            if (!items.length) {
                panel.innerHTML = `<div style="color:#a58f6b;">No service records yet.</div>`;
                return;
            }
            panel.innerHTML = items.map((record) => {
                const tech = escapeHtml(record.tech || "Tech");
                const customer = escapeHtml(record.customer || "Customer");
                const services = Array.isArray(record.selectedServices) ? escapeHtml(record.selectedServices.join(", ")) : "No services";
                const completed = record.completedAt ? new Date(record.completedAt).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "";
                const total = Number(record.total || 0).toFixed(2);
                return `<div class="activity-row"><span style="color:#f5f0e8;">${tech} • ${customer}<div style="color:#a58f6b;font-size:12px;">${services} • $${total}</div></span><span class="activity-time">${completed}</span></div>`;
            }).join("");
        }

        async function fetchServiceHistory() {
            if (!managerAuthToken) return;
            try {
                const { ok, data } = await apiRequest("/api/services/history", { token: managerAuthToken });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not load service history.");
                }
                renderServiceHistory(data.records || []);
            } catch (error) {
                renderServiceHistory([]);
            }
        }

        async function recordServiceHistoryFromFrontDesk(entry) {
            try {
                await fetch("/api/services/record", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        tech: entry.tech,
                        customer: entry.customer,
                        selectedServiceIndexes: entry.selectedServiceIndexes || [],
                        customAddons: entry.customAddons || [],
                        completedAt: entry.completedAt,
                        source: "frontdesk"
                    })
                });
            } catch (error) {
                // local service completion still succeeds
            }
        }

        function renderManagerActivityLog() {
            const container = document.getElementById("managerActivityLog");
            if (!container) return;
            if (!managerActivityLog.length) {
                container.innerHTML = `<div style="color:#a58f6b;font-size:13px;">No manager actions yet.</div>`;
                return;
            }
            container.innerHTML = managerActivityLog.slice(0, 12).map((entry) => {
                const time = new Date(entry.timestamp).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
                const color = entry.level === "error" ? "#ffd9d9" : "#f5f0e8";
                const actor = escapeHtml(entry.actor || "Manager");
                return `<div class="activity-row"><span style="color:${color};"><strong>${actor}:</strong> ${escapeHtml(entry.message)}</span><span class="activity-time">${time}</span></div>`;
            }).join("");
        }

        function clearManagerActivityLog() {
            managerActivityLog = [];
            localStorage.setItem(managerActivityLogKey, JSON.stringify(managerActivityLog));
            renderManagerActivityLog();
            showManagerMessage("Manager activity log cleared.");
            showActionToast("Manager activity log cleared.", false);
            clearManagerActivityOnServer();
        }

        async function clearManagerActivityOnServer() {
            try {
                if (managerAuthToken) {
                    await apiRequest("/api/manager/activity", { method: "DELETE", token: managerAuthToken });
                }
            } catch (error) {
                // Ignore delete failures; local clear already completed.
            }
        }

        async function copyManagerActivityLog() {
            const text = managerActivityLog
                .map((entry) => `${new Date(entry.timestamp).toLocaleString()} - ${(entry.actor || "Manager")} - ${entry.level.toUpperCase()} - ${entry.message}`)
                .join("\n");
            if (!text) {
                showActionToast("No activity log entries to copy.", true);
                return;
            }
            try {
                await navigator.clipboard.writeText(text);
                showActionToast("Manager activity log copied.", false);
            } catch (error) {
                showActionToast("Copy failed. Clipboard access unavailable.", true);
            }
        }

        function updateCurrentManagerLabel() {
            const label = document.getElementById("currentManagerLabel");
            if (!label) return;
            if (!currentManagerUsername) {
                label.textContent = "Signed in manager: --";
                return;
            }
            const full = currentManagerFullName || currentManagerUsername;
            label.textContent = `Signed in manager: ${full} (${currentManagerUsername})`;
        }

        async function fetchManagerAccounts() {
            const panel = document.getElementById("managerAccountsPanel");
            if (!panel) return;
            try {
                const { ok, data } = await apiRequest("/api/manager/accounts", { token: managerAuthToken });
                if (!ok || !data.ok) throw new Error(data.error || "Could not load manager accounts.");
                const managers = Array.isArray(data.managers) ? data.managers : [];
                if (!managers.length) {
                    panel.innerHTML = `<div style="color:#a58f6b;">No manager accounts configured.</div>`;
                    return;
                }
                panel.innerHTML = managers
                    .map((manager) => `<div class="activity-row"><span>${escapeHtml(manager.fullName || manager.username || "")} (${escapeHtml(manager.username || "")})</span></div>`)
                    .join("");
            } catch (error) {
                panel.innerHTML = `<div style="color:#ffd9d9;">${escapeHtml(error.message || "Could not load manager accounts.")}</div>`;
            }
        }

        async function createManagerAccount() {
            const fullName = document.getElementById("newManagerFullNameInput").value.trim();
            const username = document.getElementById("newManagerUsernameInput").value.trim().toLowerCase();
            const pin = document.getElementById("newManagerCreatePinInput").value.trim();
            if (!fullName || !username || !pin) {
                showManagerMessage("Enter full name, username, and PIN for new manager.", true);
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/manager/create-account", {
                    method: "POST",
                    token: managerAuthToken,
                    body: { fullName, username, pin }
                });
                if (!ok || !data.ok) throw new Error(data.error || "Could not create manager account.");
                document.getElementById("newManagerFullNameInput").value = "";
                document.getElementById("newManagerUsernameInput").value = "";
                document.getElementById("newManagerCreatePinInput").value = "";
                showManagerMessage(`Manager account created for ${fullName}.`);
                showActionToast(`Manager account created: ${username}`, false);
                addManagerActivity(`Created manager account for ${fullName} (${username}).`, "success");
                fetchManagerAccounts();
            } catch (error) {
                showManagerMessage(error.message || "Could not create manager account.", true);
                showActionToast(error.message || "Could not create manager account.", true);
                addManagerActivity(`Failed manager account create for ${username || "unknown"}.`, "error");
            }
        }

        async function exportSalonData() {
            await fetchManagerActivityLog();
            const payload = {
                exportedAt: new Date().toISOString(),
                app: "NailQue",
                version: "1.0.0",
                data: {
                    queueState: JSON.parse(localStorage.getItem(queueStateKey) || "null"),
                    serviceRecords: JSON.parse(localStorage.getItem(serviceRecordsKey) || "[]"),
                    bonusSettings: JSON.parse(localStorage.getItem(bonusSettingsKey) || "null"),
                    bonusClockIns: JSON.parse(localStorage.getItem(bonusClockInsKey) || "{}"),
                    managerActivityLog: JSON.parse(localStorage.getItem(managerActivityLogKey) || "[]"),
                    nailTechNames: JSON.parse(localStorage.getItem("nailTechNames") || "[]"),
                    nailTechCredentialMeta: getCredentialMeta(),
                    theme: localStorage.getItem(queueThemeKey) || "dark"
                }
            };
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            const dateTag = new Date().toISOString().slice(0, 10);
            anchor.href = url;
            anchor.download = `nailque-backup-${dateTag}.json`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);
            showActionToast("Salon data exported.", false);
            addManagerActivity("Exported salon backup file.", "success");
        }

        function triggerImportSalonData() {
            const input = document.getElementById("importSalonDataInput");
            if (!input) return;
            input.value = "";
            input.click();
        }

        function applyImportedSalonData(payload) {
            if (!payload || !payload.data || typeof payload.data !== "object") {
                throw new Error("Invalid backup format.");
            }
            const data = payload.data;
            if (data.queueState !== undefined && data.queueState !== null) {
                localStorage.setItem(queueStateKey, JSON.stringify(data.queueState));
            }
            if (Array.isArray(data.serviceRecords)) {
                localStorage.setItem(serviceRecordsKey, JSON.stringify(data.serviceRecords));
            }
            if (data.bonusSettings && data.bonusSettings.start && data.bonusSettings.end) {
                localStorage.setItem(bonusSettingsKey, JSON.stringify(data.bonusSettings));
            }
            if (data.bonusClockIns && typeof data.bonusClockIns === "object") {
                localStorage.setItem(bonusClockInsKey, JSON.stringify(data.bonusClockIns));
            }
            if (Array.isArray(data.managerActivityLog)) {
                localStorage.setItem(managerActivityLogKey, JSON.stringify(data.managerActivityLog));
                replaceManagerActivityOnServer(data.managerActivityLog);
            }
            if (Array.isArray(data.nailTechNames)) {
                localStorage.setItem("nailTechNames", JSON.stringify(data.nailTechNames));
            }
            if (data.nailTechCredentialMeta && typeof data.nailTechCredentialMeta === "object") {
                saveCredentialMeta(data.nailTechCredentialMeta);
            }
            if (data.nailTechCredentials && typeof data.nailTechCredentials === "object" && managerAuthToken) {
                apiRequest("/api/manager/credentials/import", {
                    method: "POST",
                    token: managerAuthToken,
                    body: { credentials: data.nailTechCredentials }
                }).then(() => {
                    credentialsConfiguredOnServer = true;
                    localStorage.removeItem("nailTechCredentials");
                }).catch(() => {});
            }
            if (data.theme === "light" || data.theme === "dark") {
                localStorage.setItem(queueThemeKey, data.theme);
            }
        }

        async function replaceManagerActivityOnServer(records) {
            try {
                const { ok, data } = await apiRequest("/api/manager/activity", {
                    method: "PUT",
                    token: managerAuthToken,
                    body: { records: Array.isArray(records) ? records : [] }
                });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not replace manager activity log.");
                }
                await fetchManagerActivityLog();
            } catch (error) {
                // Imported local backup still applies even if server replacement fails.
            }
        }

        function openManagerAccess() {
            if (document.getElementById("managerModal").style.display === "flex") {
                return;
            }
            const pinModal = document.getElementById("managerPinModal");
            const userInput = document.getElementById("managerUsernameGateInput");
            const pinInput = document.getElementById("managerPinGateInput");
            const pinMsg = document.getElementById("managerPinGateMessage");
            userInput.value = "";
            pinInput.value = "";
            pinMsg.textContent = "";
            pinMsg.style.color = "#c48b6f";
            pinModal.style.display = "flex";
            setTimeout(() => userInput.focus(), 50);
        }

        function closeManagerPinModal() {
            document.getElementById("managerPinModal").style.display = "none";
            document.getElementById("managerUsernameGateInput").value = "";
            document.getElementById("managerPinGateInput").value = "";
            document.getElementById("managerPinGateMessage").textContent = "";
        }

        async function submitManagerPinGate() {
            const username = document.getElementById("managerUsernameGateInput").value.trim().toLowerCase();
            const entered = document.getElementById("managerPinGateInput").value.trim();
            const pinMsg = document.getElementById("managerPinGateMessage");
            if (!username || !entered) {
                pinMsg.style.color = "#c48b6f";
                pinMsg.textContent = "Username and PIN are required.";
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/manager/verify-pin", {
                    method: "POST",
                    body: { username, pin: entered }
                });
                if (!ok || !data.ok || !data.token) {
                    pinMsg.style.color = "#c48b6f";
                    pinMsg.textContent = "Invalid username or PIN.";
                    return;
                }
                managerAuthToken = data.token;
                currentManagerUsername = (data.manager && data.manager.username) || username;
                currentManagerFullName = (data.manager && data.manager.fullName) || username;
                managerMustChangePin = Boolean(data.mustChangePin || (data.manager && data.manager.mustChangePin));
            } catch (error) {
                pinMsg.style.color = "#c48b6f";
                pinMsg.textContent = "Could not verify PIN. Try again.";
                return;
            }
            closeManagerPinModal();
            touchManagerActivity();
            if (managerMustChangePin) {
                openForcePinModal();
                return;
            }
            await openManagerModal();
        }

        async function openManagerModal() {
            if (pendingUpdateAfterLogin) {
                pendingUpdateAfterLogin = false;
                runOneTapUpdateFlow();
            }
            document.getElementById("bonusStartInput").value = bonusSettings.start;
            document.getElementById("bonusEndInput").value = bonusSettings.end;
            applySalonSettings(salonSettings);
            renderManagerTechList();
            await fetchManagerActivityLog();
            renderManagerActivityLog();
            fetchUpdateStatus(false);
            fetchMobileTechSessions();
            fetchServiceHistory();
            fetchManagerAccounts();
            showManagerMessage("");
            updateCurrentManagerLabel();
            document.getElementById("currentManagerPinInput").value = "";
            document.getElementById("newManagerPinInput").value = "";
            document.getElementById("newTechPasswordShow").checked = false;
            const pw = document.getElementById("newTechPassword");
            if (pw) { pw.type = "password"; }
            document.getElementById("managerModal").style.display = "flex";
            touchManagerActivity();
        }

        function closeManagerModal() {
            document.getElementById("managerModal").style.display = "none";
            currentManagerUsername = "";
            currentManagerFullName = "";
            managerAuthToken = "";
            updateCurrentManagerLabel();
        }

        function toggleNewTechPasswordVisible() {
            const show = document.getElementById("newTechPasswordShow").checked;
            const input = document.getElementById("newTechPassword");
            if (input) {
                input.type = show ? "text" : "password";
            }
        }

        async function saveBonusSettings() {
            const start = document.getElementById("bonusStartInput").value;
            const end = document.getElementById("bonusEndInput").value;
            if (!start || !end || hhmmToMinutes(start) >= hhmmToMinutes(end)) {
                showManagerMessage("Invalid bonus hours. End must be after start.", true);
                showActionToast("Bonus hours not saved: invalid time window.", true);
                addManagerActivity("Attempted to save invalid bonus window.", "error");
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/salon/settings", {
                    method: "PUT",
                    token: managerAuthToken,
                    body: { bonusHours: { start, end } }
                });
                if (!ok || !data.ok) throw new Error(data.error || "Could not save bonus hours.");
                applySalonSettings(data.settings);
                rebuildBonusOrder();
                showManagerMessage("Bonus hours saved.");
                showActionToast(`Bonus window updated: ${start} - ${end}.`, false);
                addManagerActivity(`Updated bonus window to ${start} - ${end}.`, "success");
            } catch (error) {
                showManagerMessage(error.message, true);
            }
        }

        async function setTechStatusOverride(name, status) {
            try {
                await queueMutate("status_override", { name, status, returnCustomer: status !== "Busy" });
                showActionToast(`${name} set to ${status}.`, false);
                addManagerActivity(`Set ${name} status to ${status}.`, "success");
            } catch (error) {
                showActionToast(error.message, true);
                showManagerMessage(error.message, true);
                renderManagerTechList();
            }
        }

        async function changeManagerPin() {
            if (!currentManagerUsername) {
                showManagerMessage("Manager session missing. Re-open Tech Management.", true);
                return;
            }
            const currentPin = document.getElementById("currentManagerPinInput").value.trim();
            const newPin = document.getElementById("newManagerPinInput").value.trim();
            if (!currentPin || !newPin) {
                showManagerMessage("Please enter current and new PIN.", true);
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/manager/set-pin", {
                    method: "POST",
                    token: managerAuthToken,
                    body: { username: currentManagerUsername, currentPin, newPin }
                });
                if (!ok) {
                    throw new Error(data.error || "Failed to update PIN.");
                }
                document.getElementById("currentManagerPinInput").value = "";
                document.getElementById("newManagerPinInput").value = "";
                showManagerMessage("Manager PIN updated.");
                showActionToast("Manager PIN updated.", false);
                addManagerActivity("Updated manager PIN.", "success");
            } catch (error) {
                showManagerMessage(error.message, true);
                showActionToast(error.message || "Failed to update manager PIN.", true);
                addManagerActivity("Failed to update manager PIN.", "error");
            }
        }

        async function createTechAccount() {
            const rawTechName = document.getElementById("newTechName").value.trim();
            const password = document.getElementById("newTechPassword").value.trim();
            if (!rawTechName || !password) {
                showManagerMessage("Please provide name and password.", true);
                showActionToast("Account not created: all fields are required.", true);
                addManagerActivity("Failed account create: missing required fields.", "error");
                return;
            }
            const identity = formatTechIdentity(rawTechName);
            if (!identity) {
                showManagerMessage("Use format: FirstName LastName (example: Mia Tran).", true);
                showActionToast("Account not created: name must include first and last name.", true);
                addManagerActivity(`Failed account create for ${rawTechName}: invalid name format.`, "error");
                return;
            }
            const techName = identity.techName;
            const identifier = identity.identifier;
            if (password.length < 4) {
                showManagerMessage("Password must be at least 4 characters.", true);
                showActionToast("Account not created: password must be at least 4 characters.", true);
                addManagerActivity(`Failed account create for ${techName || "unknown"}: short password.`, "error");
                return;
            }
            const normalizedTechName = techName.toLowerCase();
            const nameTaken = Object.keys(techs).some((name) => name.toLowerCase() === normalizedTechName);
            const creds = getCredentialMeta();
            const normalizedIdentifier = normalizeIdentifier(identifier);
            const identifierTaken = Object.entries(creds).some(([name, cred]) => {
                if (name.toLowerCase() === normalizedTechName) return false;
                return normalizeIdentifier(cred && cred.identifier) === normalizedIdentifier;
            });
            if (identifierTaken) {
                showManagerMessage("This login ID is already in use by another tech.", true);
                showActionToast("Account not created: login ID already in use.", true);
                addManagerActivity(`Failed account create for ${techName}: duplicate login ID.`, "error");
                return;
            }

            if (!techs[techName]) {
                techs[techName] = { status: "Offline", current: null, startTime: null, earnings: 0 };
            } else if (!nameTaken) {
                showManagerMessage("A tech with this name already exists.", true);
                showActionToast("Account not created: duplicate tech name.", true);
                addManagerActivity(`Failed account create: duplicate tech name ${techName}.`, "error");
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/manager/tech-logins", {
                    method: "POST",
                    token: managerAuthToken,
                    body: { tech: techName, identifier: identifier.trim(), password }
                });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not create tech login.");
                }
            } catch (error) {
                showManagerMessage(error.message || "Could not create tech login.", true);
                showActionToast(error.message || "Could not create tech login.", true);
                addManagerActivity(`Failed account create for ${techName}: server rejected login.`, "error");
                return;
            }
            const names = JSON.parse(localStorage.getItem("nailTechNames") || "[]");
            if (!names.includes(techName)) names.push(techName);
            localStorage.setItem("nailTechNames", JSON.stringify(names));
            creds[techName] = { identifier: identifier.trim(), mustChangePassword: true };
            saveCredentialMeta(creds);
            credentialsConfiguredOnServer = true;
            await fetchSharedStateFromServer();

            document.getElementById("newTechName").value = "";
            document.getElementById("newTechIdentifier").value = "";
            document.getElementById("newTechPassword").value = "";
            document.getElementById("newTechPasswordShow").checked = false;
            document.getElementById("newTechPassword").type = "password";
            showManagerMessage(`Account created for ${techName}.`);
            showActionToast(`Account created for ${techName}.`, false);
            addManagerActivity(`Created account for ${techName}.`, "success");
            renderManagerTechList();
        }

        async function resetTechAccountPassword(techName) {
            if (!techName || !techs[techName]) {
                showActionToast("Could not reset password: tech not found.", true);
                addManagerActivity("Failed password reset: tech not found.", "error");
                return;
            }
            const next = prompt(`New password for ${techName} (min 4 characters):`, "");
            if (next == null) return;
            const newPassword = next.trim();
            if (newPassword.length < 4) {
                showManagerMessage("Password must be at least 4 characters.", true);
                showActionToast("Password reset failed: minimum 4 characters.", true);
                addManagerActivity(`Failed password reset for ${techName}: password too short.`, "error");
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/manager/tech-logins/password", {
                    method: "POST",
                    token: managerAuthToken,
                    body: { tech: techName, password: newPassword }
                });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not reset password.");
                }
            } catch (error) {
                showManagerMessage(error.message || "Password reset failed.", true);
                showActionToast(error.message || "Password reset failed.", true);
                addManagerActivity(`Failed password reset for ${techName}.`, "error");
                return;
            }
            const creds = getCredentialMeta();
            creds[techName] = creds[techName] || {};
            creds[techName].mustChangePassword = true;
            if (!creds[techName].identifier) {
                const identity = formatTechIdentity(techName);
                creds[techName].identifier = identity ? identity.identifier : String(techName).toLowerCase().replace(/\s+/g, "");
            }
            saveCredentialMeta(creds);
            showManagerMessage(`Password updated for ${techName}.`);
            showActionToast(`Password reset for ${techName}.`, false);
            addManagerActivity(`Reset password for ${techName}.`, "success");
        }

        function openRemoveTechConfirm(techName) {
            if (!techName || !techs[techName]) return;
            pendingRemoveTechName = techName;
            const t = techs[techName];
            let msg = `Remove ${techName} from the program? This deletes their employee login.`;
            if (t.status === "Busy" && t.current) {
                msg = `${techName} is with customer "${t.current}". If you remove them, that customer will return to the top of the waiting queue and their login will be deleted.`;
            } else if (t.status === "Busy") {
                msg = `${techName} is marked busy. Remove them from the program? Their login will be deleted.`;
            }
            document.getElementById("removeTechConfirmText").textContent = msg;
            document.getElementById("removeTechConfirmModal").style.display = "flex";
        }

        function cancelRemoveTechConfirm() {
            pendingRemoveTechName = null;
            document.getElementById("removeTechConfirmModal").style.display = "none";
        }

        async function confirmRemoveTechAccount() {
            const techName = pendingRemoveTechName;
            if (!techName || !techs[techName]) {
                cancelRemoveTechConfirm();
                showActionToast("Could not remove tech: no selection.", true);
                addManagerActivity("Failed tech removal: no selection.", "error");
                return;
            }
            if (Object.keys(techs).length <= 1) {
                cancelRemoveTechConfirm();
                showManagerMessage("You must keep at least one active tech account.", true);
                showActionToast("Remove blocked: at least one tech account is required.", true);
                addManagerActivity(`Blocked removal of ${techName}: last tech protection.`, "error");
                return;
            }
            const t = techs[techName];
            lastRemovedTechSnapshot = {
                name: techName,
                tech: { ...t },
                credentialMeta: { ...(getCredentialMeta()[techName] || {}) },
                removedAt: Date.now()
            };
            try {
                await queueMutate("remove_tech", { name: techName });
            } catch (error) {
                cancelRemoveTechConfirm();
                showActionToast(error.message, true);
                return;
            }
            const creds = getCredentialMeta();
            delete creds[techName];
            saveCredentialMeta(creds);
            pendingRemoveTechName = null;
            document.getElementById("removeTechConfirmModal").style.display = "none";
            showManagerMessage(`Removed ${techName} from the program.`);
            showActionToast(`${techName} removed from the program. Use Undo if needed.`, false);
            addManagerActivity(`Removed ${techName} from the program.`, "success");
        }

        async function undoLastTechRemoval() {
            if (!lastRemovedTechSnapshot) {
                showActionToast("No recent tech removal to undo.", true);
                return;
            }
            const { name, tech, credentialMeta } = lastRemovedTechSnapshot;
            if (techs[name]) {
                showActionToast("Undo not available: tech already exists.", true);
                return;
            }
            try {
                await queueMutate("restore_tech", { name, tech });
            } catch (error) {
                showActionToast(error.message, true);
                return;
            }
            const creds = getCredentialMeta();
            creds[name] = credentialMeta && Object.keys(credentialMeta).length ? credentialMeta : {
                identifier: (formatTechIdentity(name) || {}).identifier || String(name).toLowerCase().replace(/\s+/g, ""),
                mustChangePassword: true
            };
            saveCredentialMeta(creds);
            renderTechBoard();
            renderManagerTechList();
            showActionToast(`Restored ${name}.`, false);
            addManagerActivity(`Undid removal for ${name}.`, "success");
            lastRemovedTechSnapshot = null;
        }

        function openFinishModal(techName) {
            const tech = techs[techName];
            if (tech.status !== "Busy") {
                alert(`${techName} is not currently serving a customer.`);
                return;
            }
            currentFinishingTech = techName;
            document.getElementById("finishTechName").textContent = techName;
            document.getElementById("finishCustomerNameDisplay").textContent = tech.current || "Customer";
            finishCustomAddons = [];
            let html = "";
            servicesMenu.forEach((service, i) => {
                const isNailArt = service.name === "Nail Art (per nail)";
                html += `
                <div class="service-row" onclick="toggleServiceSelection(event, ${i})">
                    <div class="service-left">
                        <input type="checkbox" onchange="calculateTotal()" data-index="${i}">
                        <span>${service.name}</span>
                        ${isNailArt ? `
                            <select
                                data-qty-index="${i}"
                                onchange="calculateTotal()"
                                style="background:#2a221b;color:#f5f0e8;border:1px solid #3d2a1f;border-radius:8px;padding:4px 8px;font-size:14px;"
                                aria-label="Nail art quantity"
                            >
                                ${Array.from({ length: 10 }, (_, n) => `<option value="${n + 1}">${n + 1}</option>`).join("")}
                            </select>
                        ` : ""}
                    </div>
                    <span class="service-price">${isNailArt ? "$5 each" : `$${service.price}`}</span>
                </div>`;
            });
            document.getElementById("serviceList").innerHTML = html;
            renderFinishCustomAddonList();
            document.getElementById("customAddonNameInput").value = "";
            document.getElementById("customAddonPriceInput").value = "";
            document.getElementById("totalAmount").textContent = "$0.00";
            document.getElementById("employeeEarnings").textContent = "$0.00";
            document.getElementById("finishModal").style.display = "flex";
        }

        function renderFinishCustomAddonList() {
            const list = document.getElementById("customAddonList");
            if (!list) return;
            if (!finishCustomAddons.length) {
                list.innerHTML = `<div style="color:#a58f6b;font-size:13px;">No custom add-ons yet.</div>`;
                return;
            }
            list.innerHTML = finishCustomAddons.map((addon, idx) => {
                return `<div class="activity-row" style="background:#1f1914;border-radius:10px;padding:8px 10px;margin-bottom:6px;"><span>${escapeHtml(addon.name)} • $${Number(addon.price || 0).toFixed(2)}</span><button type="button" class="btn-small" onclick="removeCustomAddonFromFinish(${idx})" style="background:#6b3030;color:#f5f0e8;">Remove</button></div>`;
            }).join("");
        }

        function addCustomAddonToFinish() {
            const nameInput = document.getElementById("customAddonNameInput");
            const priceInput = document.getElementById("customAddonPriceInput");
            if (!nameInput || !priceInput) return;
            const name = String(nameInput.value || "").trim();
            const price = Number(priceInput.value || 0);
            if (!name) {
                showActionToast("Enter an add-on name.", true);
                return;
            }
            if (!Number.isFinite(price) || price < 0) {
                showActionToast("Enter a valid add-on price.", true);
                return;
            }
            finishCustomAddons.push({ name: name.slice(0, 80), price: Number(price.toFixed(2)) });
            nameInput.value = "";
            priceInput.value = "";
            renderFinishCustomAddonList();
            calculateTotal();
        }

        function removeCustomAddonFromFinish(index) {
            finishCustomAddons = finishCustomAddons.filter((_, idx) => idx !== index);
            renderFinishCustomAddonList();
            calculateTotal();
        }

        function getFinishCustomAddons() {
            return finishCustomAddons.map((addon) => ({
                name: String(addon.name || "").trim(),
                price: Number(addon.price || 0),
            })).filter((addon) => addon.name && Number.isFinite(addon.price) && addon.price >= 0);
        }

        function calculateTotal() {
            let total = 0;
            document.querySelectorAll("#serviceList input:checked").forEach((cb) => {
                const idx = parseInt(cb.dataset.index, 10);
                const service = servicesMenu[idx];
                if (!service) return;
                if (service.name === "Nail Art (per nail)") {
                    const qtySelect = document.querySelector(`#serviceList select[data-qty-index="${idx}"]`);
                    const qty = qtySelect ? Math.min(10, Math.max(1, parseInt(qtySelect.value, 10) || 1)) : 1;
                    total += service.price * qty;
                } else {
                    total += service.price;
                }
            });
            getFinishCustomAddons().forEach((addon) => {
                total += Number(addon.price || 0);
            });
            document.getElementById("totalAmount").textContent = `$${total.toFixed(2)}`;
            document.getElementById("employeeEarnings").textContent = `$${(total * commissionRate).toFixed(2)}`;
        }

        function toggleServiceSelection(event, idx) {
            const target = event.target;
            if (target.closest("input, select, option")) return;
            const checkbox = document.querySelector(`#serviceList input[data-index="${idx}"]`);
            if (!checkbox) return;
            checkbox.checked = !checkbox.checked;
            calculateTotal();
        }

        async function completeServiceWithEarnings() {
            if (!currentFinishingTech) return;
            const tech = techs[currentFinishingTech];
            const completedCustomerName = tech.current || "customer";
            const selectedServiceIndexes = Array.from(document.querySelectorAll("#serviceList input:checked"))
                .map((cb) => parseInt(cb.dataset.index, 10))
                .filter((idx) => Number.isInteger(idx) && servicesMenu[idx]);
            const customAddons = getFinishCustomAddons();
            if (selectedServiceIndexes.length === 0 && customAddons.length === 0) {
                const proceed = confirm("No services selected. Complete service with $0 total?");
                if (!proceed) return;
            }
            const finishingTech = currentFinishingTech;
            try {
                const data = await queueMutate("finish", {
                    name: finishingTech,
                    selectedServiceIndexes,
                    customAddons,
                    source: "frontdesk"
                });
                document.getElementById("finishModal").style.display = "none";
                document.getElementById("finishTechName").textContent = "";
                finishCustomAddons = [];
                currentFinishingTech = null;
                showActionToast(`Service completed for ${completedCustomerName}.`, false);
                if (data.receipt) openReceiptModal(data.receipt);
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        function cancelFinishModal() {
            currentFinishingTech = null;
            finishCustomAddons = [];
            document.getElementById("finishTechName").textContent = "";
            document.getElementById("finishModal").style.display = "none";
        }

        function finishTech(name) { openFinishModal(name); }

        async function signInTech(name) {
            const tech = techs[name];
            if (!tech || tech.status === "Busy" || tech.status === "Scheduled Appointment") return;
            try {
                await queueMutate("set_status", { name, status: "Available", returnCustomer: false });
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        async function unreadyTech(name) {
            const tech = techs[name];
            if (!tech) return;
            if (tech.status === "Busy") {
                showActionToast(`${name} is busy and cannot go unready right now.`, true);
                return;
            }
            try {
                await queueMutate("set_status", { name, status: "Offline", returnCustomer: true });
                showActionToast(`${name} is now offline.`, false);
                addManagerActivity(`${name} set themselves to Offline (unready).`, "success");
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        async function toggleTechBreak(name) {
            const tech = techs[name];
            if (!tech) return;
            if (tech.status === "Busy") {
                showActionToast(`${name} is serving a customer and cannot start a break.`, true);
                return;
            }
            const nextStatus = tech.status === "On Break" ? "Available" : "On Break";
            try {
                await queueMutate("set_status", { name, status: nextStatus, returnCustomer: true });
                showActionToast(nextStatus === "Available" ? `${name} is back from break.` : `${name} is now on break.`, false);
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        async function skipNextForTech(name) {
            try {
                await queueMutate("skip_turn", { name });
                showActionToast(`${name} skipped this turn.`, false);
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        function openAddCustomerModal() {
            document.getElementById("customerNameInput").value = "";
            document.getElementById("isAppointmentInput").checked = false;
            document.getElementById("appointmentTimeInput").value = "";
            populateRequestedTechOptions();
            toggleAppointmentFields();
            document.getElementById("addCustomerModal").style.display = "flex";
            setTimeout(() => document.getElementById("customerNameInput").focus(), 0);
        }

        function closeAddCustomerModal() {
            document.getElementById("addCustomerModal").style.display = "none";
        }

        async function submitAddCustomerModal() {
            const name = document.getElementById("customerNameInput").value.trim();
            const isAppointment = document.getElementById("isAppointmentInput").checked;
            const appointmentTimeValue = document.getElementById("appointmentTimeInput").value;
            const requestedTech = document.getElementById("requestedTechInput").value;
            if (!name) {
                alert("Please enter customer name.");
                return;
            }
            if (isAppointment && !appointmentTimeValue) {
                alert("Please enter appointment time.");
                return;
            }
            let appointmentTime = null;
            if (isAppointment && appointmentTimeValue) {
                const [h, m] = appointmentTimeValue.split(":").map((v) => parseInt(v, 10));
                const appointmentDate = new Date();
                appointmentDate.setHours(h, m, 0, 0);
                appointmentTime = appointmentDate.getTime();
            }
            try {
                if (isAppointment) {
                    await queueMutate("add_appointment", {
                        name,
                        appointmentTime,
                        requestedTech: requestedTech || ""
                    });
                    showActionToast(`${name} booked for ${formatAppointmentLabel(appointmentTime)}.`, false);
                } else {
                    await queueMutate("add_customer", {
                        name,
                        requestedTech: requestedTech || "",
                        appointmentTime
                    });
                    showActionToast(`${name} added to queue.`, false);
                }
                closeAddCustomerModal();
            } catch (error) {
                alert(error.message);
            }
        }

        function toggleAppointmentFields() {
            const isAppointment = document.getElementById("isAppointmentInput").checked;
            const wrapper = document.getElementById("appointmentFields");
            wrapper.style.display = isAppointment ? "block" : "none";
        }

        function populateRequestedTechOptions() {
            const select = document.getElementById("requestedTechInput");
            const previous = select.value;
            let options = `<option value="">No preference (next available)</option>`;
            Object.keys(techs).forEach((techName) => {
                options += `<option value="${escapeHtml(techName)}">${escapeHtml(techName)}</option>`;
            });
            select.innerHTML = options;
            if (Object.keys(techs).includes(previous)) {
                select.value = previous;
            } else {
                select.value = "";
            }
        }

        function saveServiceRecord(record) {
            const existing = JSON.parse(localStorage.getItem(serviceRecordsKey) || "[]");
            existing.push(record);
            localStorage.setItem(serviceRecordsKey, JSON.stringify(existing));
        }

        function saveQueueState() {
            localStorage.setItem(queueStateKey, JSON.stringify({ techs, waitingQueue, nextCustomerId, appointments }));
        }

        function loadQueueState() {
            const saved = JSON.parse(localStorage.getItem(queueStateKey) || "null");
            if (!saved) return;
            if (saved.techs && typeof saved.techs === "object") techs = saved.techs;
            if (Array.isArray(saved.waitingQueue)) {
                waitingQueue = saved.waitingQueue.map((customer) => ({
                    ...customer,
                    appointmentTime: customer.appointmentTime || null,
                    requestedTech: customer.requestedTech || ""
                }));
            }
            if (Number.isInteger(saved.nextCustomerId)) nextCustomerId = saved.nextCustomerId;
        }

        function initializeSharedTechConfig() {
            const techNames = Object.keys(techs);
            localStorage.setItem("nailTechNames", JSON.stringify(techNames));
            const existingMeta = getCredentialMeta();
            const legacy = getLegacyCredentialsForMigration();
            if (legacy && Object.keys(legacy).length) {
                Object.assign(existingMeta, credentialMetaFromLegacy(legacy));
            }
            techNames.forEach((name) => {
                if (!existingMeta[name]) {
                    existingMeta[name] = {
                        identifier: String(name).toLowerCase().replace(/\s+/g, ""),
                        mustChangePassword: true
                    };
                }
            });
            saveCredentialMeta(existingMeta);
        }

        function loadBonusSettings() {
            const saved = JSON.parse(localStorage.getItem(bonusSettingsKey) || "null");
            if (saved && saved.start && saved.end) bonusSettings = saved;
            const savedClockIns = JSON.parse(localStorage.getItem(bonusClockInsKey) || "{}");
            if (savedClockIns && typeof savedClockIns === "object") bonusClockIns = savedClockIns;
            const savedActivity = JSON.parse(localStorage.getItem(managerActivityLogKey) || "[]");
            if (Array.isArray(savedActivity)) managerActivityLog = savedActivity;
        }

        function toggleFullscreen() {
            if (!document.fullscreenElement) document.documentElement.requestFullscreen();
            else document.exitFullscreen();
        }

        function toggleTheme() {
            document.body.classList.toggle("light-theme");
            const mode = document.body.classList.contains("light-theme") ? "light" : "dark";
            localStorage.setItem(queueThemeKey, mode);
            showActionToast(`Theme set to ${mode}.`, false);
        }

        async function openMobileAccessModal() {
            try {
                const response = await fetch("/api/network-info");
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Unable to load mobile access link.");
                }
                mobileAccessUrl = data.mobile_url || "";
                document.getElementById("mobileAccessUrl").textContent = mobileAccessUrl;
                const qrImage = document.getElementById("mobileQrImage");
                const qrDataUrl = data.mobile_qr_data_url || "";
                if (qrDataUrl) {
                    qrImage.src = qrDataUrl;
                    qrImage.style.display = "block";
                } else {
                    qrImage.removeAttribute("src");
                    qrImage.style.display = "none";
                }
                document.getElementById("mobileAccessModal").style.display = "flex";
            } catch (error) {
                showActionToast(error.message || "Could not open mobile access.", true);
            }
        }

        function closeMobileAccessModal() {
            document.getElementById("mobileAccessModal").style.display = "none";
        }

        async function copyMobileAccessUrl() {
            if (!mobileAccessUrl) return;
            try {
                await navigator.clipboard.writeText(mobileAccessUrl);
                showActionToast("Mobile link copied.", false);
            } catch (error) {
                showActionToast("Could not copy link.", true);
            }
        }

        function updateClock() {
            const clock = document.getElementById("clock");
            clock.textContent = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
        }

        async function skipWaitingCustomer(customerId) {
            try {
                await queueMutate("skip_customer", { id: customerId });
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        async function removeWaitingCustomer(customerId) {
            try {
                await queueMutate("remove_customer", { id: customerId });
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        async function arriveAppointment(appointmentId) {
            try {
                await queueMutate("arrive_appointment", { id: appointmentId });
                showActionToast("Guest moved to the waiting queue.", false);
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        async function cancelAppointment(appointmentId) {
            try {
                await queueMutate("cancel_appointment", { id: appointmentId });
                showActionToast("Appointment cancelled.", false);
            } catch (error) {
                showActionToast(error.message, true);
            }
        }

        function renderSalonServicesEditor() {
            const el = document.getElementById("salonServicesEditor");
            if (!el) return;
            if (!servicesMenu.length) {
                el.innerHTML = `<div style="color:#a58f6b;">No services yet.</div>`;
                return;
            }
            el.innerHTML = servicesMenu.map((service, idx) => {
                return `<div class="activity-row" style="background:#2a221b;border-radius:10px;padding:8px 10px;margin-bottom:6px;">
                    <span>${escapeHtml(service.name)} • $${Number(service.price || 0).toFixed(2)}</span>
                    <button type="button" class="btn-small" style="background:#6b3030;color:#f5f0e8;" onclick="removeSalonServiceRow(${idx})">Remove</button>
                </div>`;
            }).join("");
        }

        function addSalonServiceRow() {
            const name = document.getElementById("newServiceNameInput").value.trim();
            const price = Number(document.getElementById("newServicePriceInput").value);
            if (!name || !Number.isFinite(price) || price < 0) {
                showManagerMessage("Enter a service name and valid price.", true);
                return;
            }
            servicesMenu = servicesMenu.concat([{ name: name.slice(0, 80), price: Number(price.toFixed(2)) }]);
            document.getElementById("newServiceNameInput").value = "";
            document.getElementById("newServicePriceInput").value = "";
            renderSalonServicesEditor();
        }

        function removeSalonServiceRow(index) {
            servicesMenu = servicesMenu.filter((_, idx) => idx !== index);
            renderSalonServicesEditor();
        }

        async function saveSalonServicesFromManager() {
            try {
                const { ok, data } = await apiRequest("/api/salon/settings", {
                    method: "PUT",
                    token: managerAuthToken,
                    body: { services: servicesMenu }
                });
                if (!ok || !data.ok) throw new Error(data.error || "Could not save menu.");
                applySalonSettings(data.settings);
                showManagerMessage("Service menu saved.");
                addManagerActivity("Updated salon service menu.", "success");
            } catch (error) {
                showManagerMessage(error.message, true);
            }
        }

        async function saveSalonSettingsFromManager() {
            const salonName = document.getElementById("salonNameInput").value.trim();
            const tagline = document.getElementById("salonTaglineInput").value.trim();
            const percent = Number(document.getElementById("commissionRateInput").value);
            const idle = Number(document.getElementById("idleLockInput").value);
            try {
                const { ok, data } = await apiRequest("/api/salon/settings", {
                    method: "PUT",
                    token: managerAuthToken,
                    body: {
                        salonName,
                        tagline,
                        commissionRate: percent / 100,
                        idleLockMinutes: idle
                    }
                });
                if (!ok || !data.ok) throw new Error(data.error || "Could not save salon settings.");
                applySalonSettings(data.settings);
                showManagerMessage("Salon settings saved.");
                addManagerActivity("Updated salon settings.", "success");
            } catch (error) {
                showManagerMessage(error.message, true);
            }
        }

        async function runEndOfDay() {
            if (!confirm("End of day will clear the waiting list and clock every tech out. Continue?")) return;
            try {
                const { ok, data } = await apiRequest("/api/salon/end-of-day", {
                    method: "POST",
                    token: managerAuthToken,
                    body: {}
                });
                if (!ok || !data.ok) throw new Error(data.error || "End of day failed.");
                if (data.state) applySharedStateFromServer(data.state);
                todayServiceCount = 0;
                showManagerMessage("Day closed. Waiting list cleared.");
                showActionToast("End of day complete.", false);
                addManagerActivity("Ran end of day close.", "success");
            } catch (error) {
                showManagerMessage(error.message, true);
            }
        }

        function openReceiptModal(receipt) {
            lastReceipt = receipt;
            const body = document.getElementById("receiptModalBody");
            if (!body) return;
            const services = (receipt.selectedServices || []).join(", ") || "No catalog items";
            body.innerHTML = `<div><strong>${escapeHtml(receipt.salonName || "NailQue")}</strong></div>
                <div style="margin-top:8px;">${escapeHtml(receipt.customer || "Guest")} • ${escapeHtml(receipt.tech || "")}</div>
                <div style="color:#a58f6b;margin-top:8px;">${escapeHtml(services)}</div>
                <div style="margin-top:12px;font-size:22px;color:#d4af77;">$${Number(receipt.total || 0).toFixed(2)}</div>
                <div style="color:#a58f6b;">Tech share: $${Number(receipt.employeeShare || 0).toFixed(2)}</div>`;
            document.getElementById("receiptModal").style.display = "flex";
        }

        function closeReceiptModal() {
            document.getElementById("receiptModal").style.display = "none";
        }

        function printCurrentReceipt() {
            if (!lastReceipt || !lastReceipt.receiptId) return;
            window.open("/receipt/" + encodeURIComponent(lastReceipt.receiptId), "_blank");
        }

        function touchManagerActivity() {
            lastManagerActivityAt = Date.now();
        }

        function openForcePinModal() {
            document.getElementById("forceCurrentPinInput").value = "";
            document.getElementById("forceNewPinInput").value = "";
            document.getElementById("forceNewPinConfirmInput").value = "";
            document.getElementById("forcePinMessage").textContent = "";
            document.getElementById("forcePinModal").style.display = "flex";
        }

        async function submitForcedPinChange() {
            const msg = document.getElementById("forcePinMessage");
            const currentPin = document.getElementById("forceCurrentPinInput").value.trim();
            const newPin = document.getElementById("forceNewPinInput").value.trim();
            const confirmPin = document.getElementById("forceNewPinConfirmInput").value.trim();
            if (!currentPin || !newPin) {
                msg.textContent = "Enter the current and new PIN.";
                return;
            }
            if (newPin !== confirmPin) {
                msg.textContent = "New PINs do not match.";
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/manager/set-pin", {
                    method: "POST",
                    token: managerAuthToken,
                    body: { currentPin, newPin }
                });
                if (!ok) throw new Error(data.error || "Could not update PIN.");
                managerMustChangePin = false;
                document.getElementById("forcePinModal").style.display = "none";
                showActionToast("Manager PIN updated.", false);
                await openManagerModal();
            } catch (error) {
                msg.textContent = error.message;
            }
        }

        async function init() {
            const setup = await apiRequest("/api/setup/status");
            if (setup.ok && setup.data && setup.data.setupComplete === false) {
                window.location.replace("/setup");
                return;
            }
            loadBonusSettings();
            const loadedFromServer = await fetchSharedStateFromServer();
            if (!loadedFromServer) loadQueueState();
            initializeSharedTechConfig();
            if (credentialsConfiguredOnServer) {
                localStorage.removeItem("nailTechCredentials");
            }
            const savedTheme = localStorage.getItem(queueThemeKey);
            if (savedTheme === "light") document.body.classList.add("light-theme");
            renderTechBoard();
            renderQueue();
            renderAppointments();
            const managerTechList = document.getElementById("managerTechList");
            managerTechList.addEventListener("click", onManagerTechListClick);
            managerTechList.addEventListener("change", onManagerTechListChange);
            document.getElementById("managerModal").addEventListener("pointerdown", touchManagerActivity);
            document.getElementById("managerModal").addEventListener("keydown", touchManagerActivity);
            document.getElementById("customerNameInput").addEventListener("keydown", (event) => {
                if (event.key === "Enter") submitAddCustomerModal();
            });
            document.getElementById("newTechPassword").addEventListener("keydown", (event) => {
                if (event.key === "Enter") createTechAccount();
            });
            document.getElementById("newTechName").addEventListener("input", (event) => {
                const identity = formatTechIdentity(event.target.value || "");
                document.getElementById("newTechIdentifier").value = identity ? identity.identifier : "";
            });
            document.getElementById("managerPinGateInput").addEventListener("keydown", (event) => {
                if (event.key === "Enter") submitManagerPinGate();
            });
            document.getElementById("managerUsernameGateInput").addEventListener("keydown", (event) => {
                if (event.key === "Enter") submitManagerPinGate();
            });
            document.getElementById("newManagerFullNameInput").addEventListener("input", (event) => {
                const raw = String(event.target.value || "").trim().toLowerCase();
                const generated = raw.replace(/[^a-z0-9]+/g, ".").replace(/^\.+|\.+$/g, "");
                const usernameInput = document.getElementById("newManagerUsernameInput");
                if (usernameInput && !usernameInput.value) {
                    usernameInput.value = generated;
                }
            });
            document.getElementById("managerPinModal").addEventListener("click", (event) => {
                if (event.target.id === "managerPinModal") closeManagerPinModal();
            });
            document.addEventListener("keydown", (event) => {
                if (event.key !== "Escape") return;
                if (document.getElementById("removeTechConfirmModal").style.display === "flex") cancelRemoveTechConfirm();
                else if (document.getElementById("managerPinModal").style.display === "flex") closeManagerPinModal();
                else if (document.getElementById("managerModal").style.display === "flex") closeManagerModal();
                else if (document.getElementById("finishModal").style.display === "flex") cancelFinishModal();
                else if (document.getElementById("addCustomerModal").style.display === "flex") closeAddCustomerModal();
            });
            document.getElementById("addCustomerModal").addEventListener("click", (event) => {
                if (event.target.id === "addCustomerModal") closeAddCustomerModal();
            });
            document.getElementById("finishModal").addEventListener("click", (event) => {
                if (event.target.id === "finishModal") cancelFinishModal();
            });
            document.getElementById("managerModal").addEventListener("click", (event) => {
                if (event.target.id === "managerModal") closeManagerModal();
            });
            document.getElementById("removeTechConfirmModal").addEventListener("click", (event) => {
                if (event.target.id === "removeTechConfirmModal") cancelRemoveTechConfirm();
            });
            document.getElementById("mobileAccessModal").addEventListener("click", (event) => {
                if (event.target.id === "mobileAccessModal") closeMobileAccessModal();
            });
            document.getElementById("importSalonDataInput").addEventListener("change", (event) => {
                const file = event.target.files && event.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = () => {
                    try {
                        const payload = JSON.parse(String(reader.result || ""));
                        if (!confirm("Import backup and overwrite current local data?")) return;
                        applyImportedSalonData(payload);
                        loadQueueState();
                        loadBonusSettings();
                        const savedThemeAfterImport = localStorage.getItem(queueThemeKey);
                        document.body.classList.toggle("light-theme", savedThemeAfterImport === "light");
                        renderTechBoard();
                        renderQueue();
                        renderManagerTechList();
                        renderManagerActivityLog();
                        showActionToast("Salon backup imported successfully.", false);
                        addManagerActivity("Imported salon backup file.", "success");
                    } catch (error) {
                        showActionToast("Import failed: invalid backup file.", true);
                        addManagerActivity("Failed to import salon backup.", "error");
                    }
                };
                reader.readAsText(file);
            });
            setInterval(() => {
                updateClock();
                renderTechBoard();
                renderQueue();
            }, 1000);
            setInterval(() => {
                fetchUpdateStatus(false);
            }, 30000);
            setInterval(() => {
                const managerOpen = document.getElementById("managerModal").style.display === "flex";
                if (managerOpen) fetchMobileTechSessions();
            }, 10000);
            setInterval(() => {
                const managerOpen = document.getElementById("managerModal").style.display === "flex";
                if (managerOpen) fetchServiceHistory();
            }, 12000);
            setInterval(() => {
                fetchSharedStateFromServer();
            }, 2000);
            setInterval(() => {
                const managerOpen = document.getElementById("managerModal").style.display === "flex";
                if (!managerOpen || !managerAuthToken) return;
                const idleMs = Math.max(1, Number(salonSettings.idleLockMinutes || 5)) * 60 * 1000;
                if (Date.now() - lastManagerActivityAt >= idleMs) {
                    closeManagerModal();
                    showActionToast("Tech Management locked after idle.", true);
                }
            }, 5000);
            updateClock();
            setupSoundEffects();
            fetchUpdateStatus(false);
            setTimeout(() => playSoundEffect("startup"), 220);
            updateCurrentManagerLabel();
            console.log("%c✅ NailQue queue ready", "color:#d4af77;font-size:18px");
        }
        window.onload = init;
