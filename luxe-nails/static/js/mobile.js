let authToken = localStorage.getItem("mobileTechToken") || "";
        let techName = localStorage.getItem("mobileTechName") || "";
        let servicesMenu = [];
        let currentTechState = {};
        let mobileCustomAddons = [];
        let hadActiveCustomer = false;
        let hasRenderedState = false;
        let finishConfirmResolver = null;

        function showLogin(show) {
            document.getElementById("loginCard").classList.toggle("hidden", !show);
            document.getElementById("appCard").classList.toggle("hidden", show);
            document.getElementById("queueCard").classList.toggle("hidden", show);
            document.getElementById("techOrderCard").classList.toggle("hidden", show);
            document.getElementById("employeeStatsCard").classList.toggle("hidden", show);
            document.getElementById("serviceCard").classList.toggle("hidden", show);
            document.getElementById("historyCard").classList.toggle("hidden", show);
        }

        function statusClass(status) {
            return String(status || "Offline").replace(/\s+/g, "\\ ");
        }

        function renderState(payload) {
            techName = payload.tech || techName || "Tech";
            localStorage.setItem("mobileTechName", techName);
            document.getElementById("techNameLabel").textContent = `Logged in as ${techName}`;
            const status = payload.techState && payload.techState.status ? payload.techState.status : "Offline";
            const current = payload.techState && payload.techState.current ? payload.techState.current : "";
            currentTechState = payload.techState || {};
            servicesMenu = Array.isArray(payload.servicesMenu) ? payload.servicesMenu : [];
            window.nailqueCommissionRate = Number(payload.commissionRate || 0.6);
            const hasActiveCustomer = status === "Busy" && !!current;
            if (hasRenderedState && hasActiveCustomer && !hadActiveCustomer) {
                playCustomerChime();
            }
            hadActiveCustomer = hasActiveCustomer;
            hasRenderedState = true;
            document.getElementById("serviceCard").classList.toggle("hidden", !hasActiveCustomer);
            if (!hasActiveCustomer) {
                mobileCustomAddons = [];
            }
            document.getElementById("appCard").classList.toggle("tech-has-customer", hasActiveCustomer);
            document.getElementById("unreadyBtn").classList.toggle("btn-offline-active", status === "Offline");
            const customerToneClass = hasActiveCustomer ? "tech-customer-name" : "";
            document.getElementById("techStatus").innerHTML = `<span class="status-pill ${statusClass(status)}">${status.toUpperCase()}</span>${current ? ` <span class="${customerToneClass}" style="color:${hasActiveCustomer ? "#9be3ca" : "#a58f6b"};">• ${current}</span>` : ""}`;
            const queue = Array.isArray(payload.waitingQueue) ? payload.waitingQueue : [];
            const queueList = document.getElementById("queueList");
            if (!queue.length) {
                queueList.innerHTML = `<div style="color:#a58f6b;">No customers waiting.</div>`;
            } else {
                queueList.innerHTML = queue.map((customer, idx) => {
                    const requested = customer.requestedTech ? ` • request ${customer.requestedTech}` : "";
                    return `<div class="queue-item"><strong>#${idx + 1}</strong> ${customer.name}${requested}</div>`;
                }).join("");
            }
            renderTechOrder(payload.techsOverview || []);
            renderEmployeeStats(payload.serviceHistory || []);
            if (hasActiveCustomer) {
                renderServiceSelector();
            }
            renderHistory(payload.serviceHistory || []);
        }

        function renderTechOrder(techsOverview) {
            const list = document.getElementById("techOrderList");
            if (!Array.isArray(techsOverview) || !techsOverview.length) {
                list.innerHTML = `<div class="tiny">No techs available.</div>`;
                return;
            }
            list.innerHTML = techsOverview.map((item) => {
                const status = item.status || "Offline";
                const current = item.current ? ` • ${item.current}` : "";
                const bonus = item.hasBonusRound ? `<span class="bonus-tag">★ BONUS ROUND</span>` : "";
                const bonusQueue = item.bonusQueuePosition ? ` • bonus #${item.bonusQueuePosition}` : "";
                return `<div class="queue-item"><strong>${item.name}</strong> <span class="status-pill ${statusClass(status)}">${status}</span>${bonus}<div class="tiny">${current || " • no current customer"}${bonusQueue}</div></div>`;
            }).join("");
        }

        function getEmployeeWeekRecords(records, selectedTech) {
            const allRecords = Array.isArray(records) ? records : [];
            const now = new Date();
            const start = new Date(now);
            start.setHours(0, 0, 0, 0);
            start.setDate(start.getDate() - 6);
            return allRecords.filter((record) => {
                if (!record || record.tech !== selectedTech || !record.completedAt) return false;
                const completed = new Date(record.completedAt);
                return completed >= start && completed <= now;
            });
        }

        function renderEmployeeStats(records) {
            const statsGrid = document.getElementById("employeeStatsGrid");
            const daily = document.getElementById("employeeDailyBreakdown");
            const mine = getEmployeeWeekRecords(records, techName);
            const totalCustomers = mine.length;
            const totalEarnings = mine.reduce((sum, item) => sum + Number(item.employeeShare || 0), 0);
            statsGrid.innerHTML = `
                <div class="metric"><div class="metric-label">THIS WEEK</div><div class="metric-value">${totalCustomers}</div><div class="tiny">Customers Served</div></div>
                <div class="metric"><div class="metric-label">EST. EARNINGS</div><div class="metric-value">$${totalEarnings.toFixed(2)}</div><div class="tiny">60% of services</div></div>
            `;
            if (!mine.length) {
                daily.innerHTML = `<div class="tiny">No completed services this week yet.</div>`;
                return;
            }
            const byDay = {};
            mine.forEach((record) => {
                const key = new Date(record.completedAt).toLocaleDateString("en-US", { weekday: "short" });
                if (!byDay[key]) byDay[key] = { customers: 0, earnings: 0 };
                byDay[key].customers += 1;
                byDay[key].earnings += Number(record.employeeShare || 0);
            });
            const orderedWeekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            daily.innerHTML = orderedWeekdays
                .filter((day) => byDay[day])
                .map((day) => `<div class="queue-item"><strong>${day}</strong><span class="tiny"> • ${byDay[day].customers} customers • $${byDay[day].earnings.toFixed(2)}</span></div>`)
                .join("");
        }

        function renderServiceSelector() {
            const list = document.getElementById("servicesList");
            if (!Array.isArray(servicesMenu) || !servicesMenu.length) {
                list.innerHTML = `<div class="tiny">No services loaded.</div>`;
                return;
            }
            const servicesHtml = servicesMenu.map((svc, idx) => {
                return `<label class="service-row"><input type="checkbox" data-svc="${idx}"><span>${svc.name}</span><span class="tiny">$${svc.price}</span></label>`;
            }).join("");
            const addOnHtml = `
                <div style="margin-top:10px;padding-top:10px;border-top:1px solid #3d2a1f;">
                    <div class="tiny" style="margin-bottom:8px;color:#d4af77;">Custom Add-on</div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <input id="mobileAddonName" class="input" type="text" placeholder="Add-on name" style="flex:1;min-width:160px;margin-bottom:0;">
                        <input id="mobileAddonPrice" class="input" type="number" min="0" step="0.01" placeholder="Price" style="width:110px;margin-bottom:0;">
                    </div>
                    <button type="button" class="btn btn-muted" style="margin-top:8px;margin-bottom:0;" onclick="addMobileCustomAddon()">ADD CUSTOM ADD-ON</button>
                    <div id="mobileAddonList" style="margin-top:8px;"></div>
                </div>
            `;
            list.innerHTML = `${servicesHtml}${addOnHtml}`;
            renderMobileCustomAddonList();
        }

        function renderMobileCustomAddonList() {
            const list = document.getElementById("mobileAddonList");
            if (!list) return;
            if (!mobileCustomAddons.length) {
                list.innerHTML = `<div class="tiny">No custom add-ons yet.</div>`;
                return;
            }
            list.innerHTML = mobileCustomAddons.map((addon, idx) => {
                return `<div class="queue-item"><strong>${addon.name}</strong> <span class="tiny">• $${Number(addon.price || 0).toFixed(2)}</span> <button type="button" class="btn btn-muted" style="width:auto;padding:6px 10px;margin:0 0 0 8px;font-size:12px;" onclick="removeMobileCustomAddon(${idx})">Remove</button></div>`;
            }).join("");
        }

        function addMobileCustomAddon() {
            const nameInput = document.getElementById("mobileAddonName");
            const priceInput = document.getElementById("mobileAddonPrice");
            if (!nameInput || !priceInput) return;
            const name = String(nameInput.value || "").trim();
            const price = Number(priceInput.value || 0);
            if (!name) {
                alert("Please enter a custom add-on name.");
                return;
            }
            if (!Number.isFinite(price) || price < 0) {
                alert("Please enter a valid custom add-on price.");
                return;
            }
            mobileCustomAddons.push({ name: name.slice(0, 80), price: Number(price.toFixed(2)) });
            nameInput.value = "";
            priceInput.value = "";
            renderMobileCustomAddonList();
        }

        function removeMobileCustomAddon(index) {
            mobileCustomAddons = mobileCustomAddons.filter((_, idx) => idx !== index);
            renderMobileCustomAddonList();
        }

        function getMobileCustomAddons() {
            return mobileCustomAddons.map((addon) => ({
                name: String(addon.name || "").trim(),
                price: Number(addon.price || 0),
            })).filter((addon) => addon.name && Number.isFinite(addon.price) && addon.price >= 0);
        }

        function renderHistory(records) {
            const list = document.getElementById("historyList");
            const items = Array.isArray(records) ? records.slice().reverse().slice(0, 25) : [];
            if (!items.length) {
                list.innerHTML = `<div class="tiny">No services recorded yet.</div>`;
                return;
            }
            list.innerHTML = items.map((r) => {
                const services = Array.isArray(r.selectedServices) ? r.selectedServices.join(", ") : "";
                const timeText = r.completedAt ? new Date(r.completedAt).toLocaleString() : "";
                return `<div class="queue-item"><strong>${r.tech || "Tech"}</strong> • ${r.customer || "Customer"}<div class="tiny">${services || "No services"} • $${Number(r.total || 0).toFixed(2)} • ${timeText}</div></div>`;
            }).join("");
        }

        function getSelectedServiceIndexes() {
            return Array.from(document.querySelectorAll("#servicesList input[type='checkbox']:checked"))
                .map((input) => parseInt(input.dataset.svc || "-1", 10))
                .filter((value) => Number.isInteger(value) && value >= 0);
        }

        function buildServiceRecap(selectedIndexes, customAddons) {
            const validIndexes = Array.isArray(selectedIndexes) ? selectedIndexes : [];
            const lines = [];
            let total = 0;
            validIndexes.forEach((idx) => {
                const svc = servicesMenu[idx];
                if (!svc) return;
                const price = Number(svc.price || 0);
                total += price;
                lines.push(`- ${svc.name}: $${price.toFixed(2)}`);
            });
            if (Array.isArray(customAddons)) {
                customAddons.forEach((addon) => {
                    const addonName = String((addon || {}).name || "").trim();
                    const addonPrice = Number((addon || {}).price || 0);
                    if (!addonName || !Number.isFinite(addonPrice) || addonPrice < 0) return;
                    total += addonPrice;
                    lines.push(`- ${addonName} (Add-on): $${addonPrice.toFixed(2)}`);
                });
            }
            const roundedTotal = Number(total.toFixed(2));
            const employeeShare = Number((roundedTotal * Number(window.nailqueCommissionRate || 0.6)).toFixed(2));
            return {
                lines,
                total: roundedTotal,
                employeeShare,
            };
        }

        async function confirmFinishCustomer(selectedIndexes, customAddons) {
            const recap = buildServiceRecap(selectedIndexes, customAddons);
            const list = document.getElementById("finishConfirmServices");
            const total = document.getElementById("finishConfirmTotal");
            const pay = document.getElementById("finishConfirmPay");
            const modal = document.getElementById("finishConfirmModal");
            if (!list || !total || !pay || !modal) {
                return window.confirm(`Customer total: $${recap.total.toFixed(2)}\nNail tech pay: $${recap.employeeShare.toFixed(2)}\n\nSubmit ticket?`);
            }
            const lines = recap.lines.length ? recap.lines : ["No services selected"];
            list.innerHTML = lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("");
            total.textContent = `$${recap.total.toFixed(2)}`;
            pay.textContent = `$${recap.employeeShare.toFixed(2)}`;
            modal.style.display = "flex";
            return new Promise((resolve) => {
                finishConfirmResolver = resolve;
            });
        }

        function closeFinishConfirmModal(confirmed) {
            const modal = document.getElementById("finishConfirmModal");
            if (modal) modal.style.display = "none";
            if (typeof finishConfirmResolver === "function") {
                const resolve = finishConfirmResolver;
                finishConfirmResolver = null;
                resolve(Boolean(confirmed));
            }
        }

        function escapeHtml(value) {
            return String(value || "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }

        async function login() {
            const identifier = document.getElementById("identifierInput").value.trim();
            const password = document.getElementById("passwordInput").value;
            document.getElementById("loginError").textContent = "";
            try {
                const response = await fetch("/api/mobile/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ identifier, password })
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || "Login failed.");
                authToken = data.token || "";
                if (data.mustChangePassword) {
                    const changed = await promptMobilePasswordChange(password);
                    if (!changed) return;
                    return await login();
                }
                techName = data.tech || "";
                localStorage.setItem("mobileTechToken", authToken);
                localStorage.setItem("mobileTechName", techName);
                showLogin(false);
                await refreshState();
            } catch (error) {
                document.getElementById("loginError").textContent = error.message || "Login failed.";
            }
        }

        async function promptMobilePasswordChange(currentPassword) {
            const next = prompt("Please set a new password before continuing (min 4 characters):", "");
            if (next == null) {
                document.getElementById("loginError").textContent = "Password update is required before login.";
                return false;
            }
            const newPassword = String(next).trim();
            if (newPassword.length < 4) {
                document.getElementById("loginError").textContent = "New password must be at least 4 characters.";
                return false;
            }
            if (newPassword === currentPassword) {
                document.getElementById("loginError").textContent = "New password must be different.";
                return false;
            }
            try {
                const response = await fetch("/api/mobile/change-password", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
                    body: JSON.stringify({ currentPassword, newPassword })
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || "Could not update password.");
                document.getElementById("passwordInput").value = newPassword;
                document.getElementById("loginError").textContent = "Password updated. Please log in again.";
                localStorage.removeItem("mobileTechToken");
                authToken = "";
                return true;
            } catch (error) {
                document.getElementById("loginError").textContent = error.message || "Password update failed.";
                return false;
            }
        }

        async function refreshState() {
            if (!authToken) {
                showLogin(true);
                return;
            }
            const response = await fetch("/api/mobile/state", {
                headers: { Authorization: `Bearer ${authToken}` }
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                localStorage.removeItem("mobileTechToken");
                authToken = "";
                showLogin(true);
                return;
            }
            showLogin(false);
            renderState(data);
        }

        async function sendAction(action) {
            if (!authToken) return;
            try {
                const payload = { action };
                if (action === "finish_customer") {
                    if (!currentTechState || currentTechState.status !== "Busy") {
                        throw new Error("You are not serving a customer right now.");
                    }
                    payload.selectedServiceIndexes = getSelectedServiceIndexes();
                    payload.customAddons = getMobileCustomAddons();
                    if (!await confirmFinishCustomer(payload.selectedServiceIndexes, payload.customAddons)) {
                        return;
                    }
                }
                const response = await fetch("/api/mobile/action", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${authToken}`
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || "Action failed.");
                await refreshState();
            } catch (error) {
                alert(error.message || "Action failed.");
            }
        }

        function playCustomerChime() {
            try {
                const Context = window.AudioContext || window.webkitAudioContext;
                if (!Context) return;
                const audioCtx = new Context();
                const now = audioCtx.currentTime;
                const notes = [523.25, 659.25, 783.99];
                notes.forEach((frequency, index) => {
                    const osc = audioCtx.createOscillator();
                    const gain = audioCtx.createGain();
                    osc.type = index === notes.length - 1 ? "triangle" : "sine";
                    osc.frequency.setValueAtTime(frequency, now + index * 0.11);
                    gain.gain.setValueAtTime(0.0001, now + index * 0.11);
                    gain.gain.exponentialRampToValueAtTime(0.095, now + index * 0.11 + 0.025);
                    gain.gain.exponentialRampToValueAtTime(0.0001, now + index * 0.11 + 0.28);
                    osc.connect(gain);
                    gain.connect(audioCtx.destination);
                    osc.start(now + index * 0.11);
                    osc.stop(now + index * 0.11 + 0.30);
                });
                setTimeout(() => {
                    audioCtx.close().catch(() => {});
                }, 620);
            } catch (error) {
                // Ignore audio errors; visual cues still indicate status change.
            }
        }

        refreshState();
        setInterval(refreshState, 4000);
