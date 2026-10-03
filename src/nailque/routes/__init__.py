from nailque.routes.manager import bp as manager_bp
from nailque.routes.mobile import bp as mobile_bp
from nailque.routes.pages import bp as pages_bp
from nailque.routes.shared import bp as shared_bp
from nailque.routes.update import bp as update_bp


def register_blueprints(app):
    app.register_blueprint(shared_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(update_bp)
    app.register_blueprint(mobile_bp)
    app.register_blueprint(pages_bp)
