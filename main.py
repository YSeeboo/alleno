from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import models  # noqa: F401 — ensures all models are registered with Base.metadata
from database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass  # allow startup without a live DB (e.g., during tests)
    yield


app = FastAPI(title="Allen Shop", description="饰品店管理系统", lifespan=lifespan)


# TODO: register routers
# from api import parts, jewelries, inventory, orders, plating, handcraft
# app.include_router(parts.router)
# app.include_router(jewelries.router)
# app.include_router(inventory.router)
# app.include_router(orders.router)
# app.include_router(plating.router)
# app.include_router(handcraft.router)

from api.bom import router as bom_router
app.include_router(bom_router)

from api.parts import router as parts_router
app.include_router(parts_router)

from api.jewelries import router as jewelries_router
app.include_router(jewelries_router)

from api.inventory import router as inventory_router
app.include_router(inventory_router)

from api.orders import router as orders_router
app.include_router(orders_router)

from api.plating import router as plating_router
app.include_router(plating_router)

from api.handcraft import router as handcraft_router
app.include_router(handcraft_router)


@app.get("/")
def root():
    return {"status": "ok", "app": "Allen Shop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
