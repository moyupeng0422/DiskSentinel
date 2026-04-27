"""DiskSentinel - C 盘文件监控与清理工具入口"""
import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db
from core.rules import init_rules
from api.routes import dashboard, snapshots, comparison, cleaner, monitor

app = FastAPI(title="DiskSentinel", version="1.0.0")

# 注册 API 路由
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["仪表盘"])
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["快照管理"])
app.include_router(comparison.router, prefix="/api/comparison", tags=["快照对比"])
app.include_router(cleaner.router, prefix="/api/cleaner", tags=["清理中心"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["实时监控"])


@app.on_event("startup")
async def startup():
    os.makedirs("data", exist_ok=True)
    init_db()
    init_rules()


@app.get("/")
async def index():
    return FileResponse("templates/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
