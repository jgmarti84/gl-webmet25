# api/app/routers/__init__.py
from .radars import router as radars_router
from .products import router as products_router
from .cogs import router as cogs_router
from .tiles import router as tiles_router

__all__ = [
    'radars_router',
    'products_router',
    'cogs_router',
    'tiles_router',
]