from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import models  # noqa: F401 — ensures all models are registered with Base.metadata
from database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Allen Shop", description="饰品店管理系统", lifespan=lifespan)


# TODO: register routers
# from api import parts, jewelries, bom, inventory, orders, plating, handcraft
# app.include_router(parts.router)
# app.include_router(jewelries.router)
# app.include_router(bom.router)
# app.include_router(inventory.router)
# app.include_router(orders.router)
# app.include_router(plating.router)
# app.include_router(handcraft.router)


@app.get("/")
def root():
    return {"status": "ok", "app": "Allen Shop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
