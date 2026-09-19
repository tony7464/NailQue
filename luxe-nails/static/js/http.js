/**
 * Small JSON helper shared by the queue, employee, and mobile pages.
 */
async function apiRequest(path, options = {}) {
    const {
        method = "GET",
        body,
        token,
        headers: extraHeaders = {},
    } = options;
    const headers = { ...extraHeaders };
    if (body !== undefined) {
        headers["Content-Type"] = "application/json";
    }
    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }
    const response = await fetch(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const contentType = response.headers.get("content-type") || "";
    let data = {};
    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        const text = await response.text();
        if (text) {
            data = { error: text };
        }
    }
    return { ok: response.ok, status: response.status, data, response };
}
