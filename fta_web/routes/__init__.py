"""
Flask blueprints for the fta_web API.

Each module here owns one blueprint and re-exports it from this package, so
``app.create_app()`` can register them with a single import:

    from fta_web.routes import tree_bp
    app.register_blueprint(tree_bp)

Every blueprint mounts under ``/api``.
"""
from .tree import tree_bp

__all__ = ["tree_bp"]
