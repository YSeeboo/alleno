import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models  # noqa: F401 — ensures all models are registered with Base.metadata
from database import Base, engine, ensure_optional_columns

from api.bom import router as bom_router
from api.parts import router as parts_router
from api.jewelries import router as jewelries_router
from api.inventory import router as inventory_router
from api.orders import router as orders_router
from api.plating import router as plating_router
from api.handcraft import router as handcraft_router
from api.uploads import router as uploads_router
from api.feishu import router as feishu_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        ensure_optional_columns()
    except Exception:
        pass  # allow startup without a live DB (e.g., during tests)
    yield


app = FastAPI(title="Allenop", description="饰品店管理系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parts_router)
app.include_router(jewelries_router)
app.include_router(bom_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(plating_router)
app.include_router(handcraft_router)
app.include_router(uploads_router)
app.include_router(feishu_router)


@app.get("/")
def root():
    return {"status": "ok", "app": "Allenop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
