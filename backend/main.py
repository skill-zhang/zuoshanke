"""坐山客 API — FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from router import register_all_routers

app = FastAPI(title="坐山客 API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_all_routers(app)

if __name__ == "__main__":
    import uvicorn

    init_db()
    print("✅ 数据库已初始化")
    uvicorn.run(app, host="0.0.0.0", port=8000)
