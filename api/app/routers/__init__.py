# api/app/routers/__init__.py
from .radars import router as radars_router
from .products import router as products_router
from .cogs import router as cogs_router
from .tiles import router as tiles_router
from .colormap import router as colormap_router
from .frames import router as frames_router
from .tops_cores import router as tops_cores_router
from .admin import router as admin_router
from .auth import router as auth_router
from .registration import router as registration_router
from .users import router as users_router
from .permissions import router as permissions_router
from .organizations import router as organizations_router
from .org import router as org_router

__all__ = [
    "radars_router",
    "products_router",
    "cogs_router",
    "tiles_router",
    "colormap_router",
    "frames_router",
    "tops_cores_router",
    "admin_router",
    "auth_router",
    "registration_router",
    "users_router",
    "permissions_router",
    "organizations_router",
    "org_router",
]
