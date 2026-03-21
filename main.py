import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — ensures all models are registered with Base.metadata
from config import settings
from database import Base, SessionLocal, engine, ensure_schema_compat
from api.deps import get_current_user, require_permission

from api.auth import router as auth_router
from api.users import router as users_router
from api.bom import router as bom_router
from api.parts import router as parts_router
from api.jewelries import router as jewelries_router
from api.inventory import router as inventory_router
from api.orders import router as orders_router
from api.plating import router as plating_router
from api.handcraft import router as handcraft_router
from api.uploads import router as uploads_router
from api.feishu import router as feishu_router
from api.kanban import router as kanban_router
from api.purchase_order import router as purchase_order_router

logger = logging.getLogger(__name__)


def _init_admin():
    """Create default admin user if not exists."""
    import secrets
    from models.user import User
    from services.auth import hash_password

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if existing is None:
            password = secrets.token_urlsafe(16)
            admin = User(
                username="admin",
                password_hash=hash_password(password),
                owner="管理员",
                permissions=[],
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            logger.warning("Created default admin user — initial password: %s", password)
            logger.warning("Please change the admin password immediately after first login.")
    except Exception as e:
        db.rollback()
        logger.warning("Admin init skipped: %s", e)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.JWT_SECRET_KEY == "allen-shop-jwt-secret-change-in-prod":
        import secrets as _secrets
        settings.JWT_SECRET_KEY = _secrets.token_urlsafe(32)
        logger.warning("JWT_SECRET_KEY was not configured — generated a random ephemeral secret. "
                        "Tokens will be invalidated on restart. Set JWT_SECRET_KEY in .env for persistence.")
    try:
        Base.metadata.create_all(bind=engine)
        ensure_schema_compat()
        _init_admin()
    except Exception as e:
        logger.warning("DB init skipped: %s", e)
    yield


app = FastAPI(title="Allenop", description="饰品店管理系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://ycbhomeland.top", "https://www.ycbhomeland.top"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes (no login required)
app.include_router(auth_router)

# User management (requires "users" permission — handled inside the router)
app.include_router(users_router)

# Protected routes with module-level permissions
app.include_router(parts_router, dependencies=[require_permission("parts")])
app.include_router(jewelries_router, dependencies=[require_permission("jewelries")])
app.include_router(bom_router, dependencies=[require_permission("parts")])
app.include_router(inventory_router, dependencies=[require_permission("inventory")])
app.include_router(orders_router, dependencies=[require_permission("orders")])
app.include_router(plating_router, dependencies=[require_permission("plating")])
app.include_router(handcraft_router, dependencies=[require_permission("handcraft")])
app.include_router(uploads_router, dependencies=[Depends(get_current_user)])
app.include_router(feishu_router)
app.include_router(kanban_router, prefix="/api/kanban", tags=["kanban"], dependencies=[require_permission("kanban")])
app.include_router(purchase_order_router, dependencies=[require_permission("purchase_orders")])


@app.get("/")
def root():
    return {"status": "ok", "app": "Allenop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
