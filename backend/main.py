from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from logging.handlers import RotatingFileHandler
from .api.routes import router
import uvicorn
import logging
import os

# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.StreamHandler()
#     ]
# )
# ----------------log setting-----------------
# log dir pending
log_dir = "./data/logs"
os.makedirs(log_dir, exist_ok=True)

#格式
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

#文件处理器
file_handler = RotatingFileHandler(
    filename=os.path.join(log_dir, 'app.log'),
    maxBytes=1024*1024*10, #10M
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

#控制台处理器
consols_handler = logging.StreamHandler()
consols_handler.setFormatter(log_formatter)
consols_handler.setLevel(logging.DEBUG)

#获取根日志记录器并添加处理器
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)

app = FastAPI(title="新闻谏言API")

#跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)#CORS跨域

app.include_router(router)

@app.get("/")
async def root():
    return {"message": "API START","status": "OK"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)