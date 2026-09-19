// ============== FULL M. VINCÉ SERVICE MENU ==============
        let servicesMenu = [];

        let currentTech = null;
        let employeeAuthToken = localStorage.getItem("employeeAuthToken") || "";
        let serviceHistoryRecords = [];
        let toastTimer = null;
        const soundFx = {
            startup: "/assets/sounds/startup_fx.mp3",
            click: "/assets/sounds/click_fx.mp3",
        };

        async function performEmployeeLogin() {
            const id = document.getElementById("loginIdentifier").value.trim().toLowerCase();
            const pass = document.getElementById("loginPassword").value;
            if (!id || !pass) {
                showToast("Please enter both fields.", true);
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/employee/login", {
                    method: "POST",
                    body: { identifier: id, password: pass }
                });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Invalid credentials.");
                }
                if (data.mustChangePassword) {
                    const changed = await promptEmployeePasswordChange(id, pass, data.tech);
                    if (!changed) return;
                    return performEmployeeLogin();
                }
                employeeAuthToken = data.token || "";
                currentTech = data.tech;
                localStorage.setItem("employeeAuthToken", employeeAuthToken);
                localStorage.setItem("employeeLastLoginId", id);
                await showDashboard();
                showToast(`Welcome, ${currentTech}.`, false);
            } catch (error) {
                showToast(error.message || "Invalid credentials.", true);
            }
        }

        async function promptEmployeePasswordChange(identifier, currentPassword, techName) {
            const nextPassword = prompt(
                `${techName}, please set a new password before continuing.\nUse at least 4 characters.`,
                ""
            );
            if (nextPassword == null) {
                showToast("Password update required before login.", true);
                return false;
            }
            const newPassword = String(nextPassword).trim();
            if (newPassword.length < 4) {
                showToast("New password must be at least 4 characters.", true);
                return false;
            }
            if (newPassword === currentPassword) {
                showToast("New password must be different.", true);
                return false;
            }
            try {
                const { ok, data } = await apiRequest("/api/tech/change-password", {
                    method: "POST",
                    body: { identifier, currentPassword, newPassword }
                });
                if (!ok || !data.ok) {
                    throw new Error(data.error || "Could not update password.");
                }
                document.getElementById("loginPassword").value = newPassword;
                showToast("Password updated. Login complete.", false);
                return true;
            } catch (error) {
                showToast(error.message || "Password update failed.", true);
                return false;
            }
        }

        async function showDashboard() {
            document.getElementById("loginScreen").style.display = "none";
            document.getElementById("dashboardScreen").style.display = "flex";
            document.getElementById("dashName").textContent = currentTech;
            await loadServiceHistory();
            renderWeeklyStats();
        }

        function logoutEmployee() {
            currentTech = null;
            employeeAuthToken = "";
            localStorage.removeItem("employeeAuthToken");
            document.getElementById("dashboardScreen").style.display = "none";
            document.getElementById("loginScreen").style.display = "flex";
            document.getElementById("loginPassword").value = "";
            document.getElementById("loginIdentifier").focus();
            showToast("Logged out.", false);
        }

        function renderWeeklyStats() {
            if (!currentTech) return;

            const records = getEmployeeWeekRecords(currentTech);
            const totalCustomers = records.length;
            const totalEarnings = records.reduce((sum, r) => sum + (r.employeeShare || 0), 0);

            document.getElementById("weekTotal").textContent = String(totalCustomers);
            document.getElementById("weekEarnings").textContent = `$${totalEarnings.toFixed(2)}`;
            renderDailyBreakdown(records);
        }

        function getEmployeeWeekRecords(techName) {
            const now = new Date();
            const start = new Date(now);
            start.setHours(0, 0, 0, 0);
            start.setDate(start.getDate() - 6);

            return serviceHistoryRecords.filter((record) => {
                if (!record || record.tech !== techName || !record.completedAt) return false;
                const completed = new Date(record.completedAt);
                return completed >= start && completed <= now;
            });
        }

        async function loadServiceHistory() {
            if (!employeeAuthToken) {
                serviceHistoryRecords = [];
                return;
            }
            try {
                const { ok, data } = await apiRequest("/api/employee/history", { token: employeeAuthToken });
                if (!ok || !data.ok || !Array.isArray(data.records)) {
                    throw new Error("History unavailable");
                }
                serviceHistoryRecords = data.records;
            } catch (error) {
                serviceHistoryRecords = [];
            }
        }

        function renderDailyBreakdown(records) {
            const dailyList = document.getElementById("dailyList");
            if (records.length === 0) {
                dailyList.innerHTML = `<div style="text-align:center; color:#a58f6b; padding:8px 0;">No completed services this week yet.</div>`;
                return;
            }

            const byDay = {};
            records.forEach((record) => {
                const key = new Date(record.completedAt).toLocaleDateString("en-US", { weekday: "short" });
                if (!byDay[key]) byDay[key] = { customers: 0, earnings: 0 };
                byDay[key].customers += 1;
                byDay[key].earnings += record.employeeShare || 0;
            });

            const orderedWeekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            dailyList.innerHTML = orderedWeekdays
                .filter((day) => byDay[day])
                .map((day) => `
                    <div class="day-row">
                        <span class="day-name">${day} (${byDay[day].customers})</span>
                        <span>$${byDay[day].earnings.toFixed(2)}</span>
                    </div>
                `)
                .join("");
        }

        // Utility available for employee-side calculations based on selected menu items
        function calculateMenuTotalByIndexes(indexes) {
            return (indexes || []).reduce((sum, idx) => {
                const item = servicesMenu[idx];
                return sum + (item ? item.price : 0);
            }, 0);
        }

        async function loadSalonBranding() {
            try {
                const { ok, data } = await apiRequest("/api/salon/settings");
                if (!ok || !data.ok || !data.settings) return;
                const name = data.settings.salonName || "NailQue";
                document.querySelectorAll("[data-salon-name]").forEach((el) => {
                    el.textContent = name;
                });
                document.title = name + " • Employee Portal";
                if (Array.isArray(data.settings.services)) servicesMenu = data.settings.services;
                const rate = Number(data.settings.commissionRate || 0.6);
                const label = document.getElementById("weekEarningsLabel");
                if (label) label.textContent = `(${Math.round(rate * 100)}% of services)`;
            } catch (error) {
                // Branding is cosmetic; login still works.
            }
        }

        async function init() {
            const savedLoginId = localStorage.getItem("employeeLastLoginId");
            if (savedLoginId) {
                document.getElementById("loginIdentifier").value = savedLoginId;
            }
            document.getElementById("showLoginPassword").addEventListener("change", (event) => {
                document.getElementById("loginPassword").type = event.target.checked ? "text" : "password";
            });
            document.getElementById("loginIdentifier").addEventListener("keydown", (event) => {
                if (event.key === "Enter") performEmployeeLogin();
            });
            document.getElementById("loginPassword").addEventListener("keydown", (event) => {
                if (event.key === "Enter") performEmployeeLogin();
            });
            await loadSalonBranding();
            setupSoundEffects();
            setTimeout(() => playSoundEffect("startup"), 220);
        }

        function showToast(message, isError) {
            const toast = document.getElementById("employeeToast");
            toast.textContent = message;
            toast.classList.toggle("error", !!isError);
            toast.style.display = "block";
            if (toastTimer) clearTimeout(toastTimer);
            toastTimer = setTimeout(() => {
                toast.style.display = "none";
            }, 2500);
        }

        function playSoundEffect(kind) {
            const src = soundFx[kind];
            if (!src) return;
            const audio = new Audio(src);
            audio.preload = "auto";
            audio.volume = 0.6;
            audio.play().catch(() => {});
        }

        function setupSoundEffects() {
            document.addEventListener("click", (event) => {
                const clickable = event.target.closest("button, [role='button'], .login-button, .logout-btn, .nav-back-btn");
                if (!clickable) return;
                playSoundEffect("click");
            }, true);
        }
        
        window.onload = init;
