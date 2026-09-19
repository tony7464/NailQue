async function submitSetup() {
    const message = document.getElementById("setupMessage");
    const salonName = document.getElementById("setupSalonName").value.trim();
    const tagline = document.getElementById("setupTagline").value.trim() || "NAIL SPA";
    const fullName = document.getElementById("setupFullName").value.trim();
    const username = document.getElementById("setupUsername").value.trim().toLowerCase();
    const pin = document.getElementById("setupPin").value.trim();
    const pinConfirm = document.getElementById("setupPinConfirm").value.trim();
    message.style.color = "#ff9b9b";
    if (!salonName || !fullName || !username || !pin) {
        message.textContent = "All fields are required.";
        return;
    }
    if (pin !== pinConfirm) {
        message.textContent = "PINs do not match.";
        return;
    }
    try {
        const { ok, data } = await apiRequest("/api/setup", {
            method: "POST",
            body: { salonName, tagline, fullName, username, pin },
        });
        if (!ok || !data.ok) {
            throw new Error(data.error || "Setup failed.");
        }
        message.style.color = "#9be3ca";
        message.textContent = "Salon ready. Opening the queue…";
        window.location.href = "/";
    } catch (error) {
        message.textContent = error.message || "Setup failed.";
    }
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Enter") submitSetup();
});

(async function redirectIfReady() {
    try {
        const { ok, data } = await apiRequest("/api/setup/status");
        if (ok && data.setupComplete) {
            window.location.replace("/");
        }
    } catch (error) {
        // Stay on the wizard if status cannot be loaded.
    }
})();
