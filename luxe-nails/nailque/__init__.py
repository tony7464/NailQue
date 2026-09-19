"""NailQue salon queue application package."""

__all__ = ["create_app"]


def create_app():
    from nailque.factory import create_app as _create_app

    return _create_app()
