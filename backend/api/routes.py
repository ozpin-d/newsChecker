from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..core.pipeline import process_news
from ..utils.text_extractor import extract_from_url

router = APIRouter(prefix="/api/v1", tags=["新闻核查"])

class NewsRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None

@router.post("/check")
async def check_news(request: NewsRequest):
    if not request.text and not request.url: #非空处理
        raise HTTPException(status_code=400, detail="请提供新闻文本或URL")
    if request.url:
        news_text = extract_from_url(request.url)
        if not news_text: #非空处理
            raise HTTPException(status_code=400, detail="无法从URL中提取新闻文本")
    else:
        news_text = request.text
    
    try:
        result = await process_news(news_text)
        import json
        print("="*50)
        print("返回给前端的 JSON：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("="*50)
        return {"success": True, "data": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DEAL ERROR:{str(e)}")

@router.get("/history")
async def get_history():
    return {"history": []}