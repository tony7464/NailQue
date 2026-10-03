import threading

from flask import Blueprint, jsonify

from nailque.updater import (
    UPDATE_STATE,
    check_for_updates,
    get_update_status,
    install_downloaded_update,
)

bp = Blueprint("update", __name__)


@bp.route("/api/update/status", methods=["GET"])
def update_status():
    return jsonify(get_update_status())


@bp.route("/api/update/check", methods=["POST"])
def trigger_update_check():
    if not UPDATE_STATE["enabled"]:
        return jsonify({"ok": False, "error": "Auto-updater is disabled. Set AUTO_UPDATE_ENABLED=true and AUTO_UPDATE_REPO=tony7464/NailQue."}), 400
    threading.Thread(target=lambda: check_for_updates(download_if_available=True), daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/update/check-sync", methods=["POST"])
def trigger_update_check_sync():
    if not UPDATE_STATE["enabled"]:
        return jsonify({"ok": False, "error": "Auto-updater is disabled. Set AUTO_UPDATE_ENABLED=true and AUTO_UPDATE_REPO=tony7464/NailQue."}), 400
    check_for_updates(download_if_available=True)
    return jsonify({"ok": True, "status": get_update_status()})


@bp.route("/api/update/install", methods=["POST"])
def install_update():
    try:
        install_downloaded_update()
        return jsonify({"ok": True, "message": "Update installed. Relaunching NailQue..."})
    except RuntimeError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
