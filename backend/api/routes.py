from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..core.pipeline import process_news
from ..utils.text_extractor import default_extractor

router = APIRouter(prefix="/api/v1", tags=["新闻核查"])

class NewsRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None

@router.post("/check")
async def check_news(request: NewsRequest):
    if not request.text and not request.url: #非空处理
        raise HTTPException(status_code=400, detail="请提供新闻文本或URL")
    
    original_url = None
    original_title = None
    news_text = None

    if request.url:
        title,text = default_extractor.extract(request.url)
        if not text: #非空处理
            raise HTTPException(status_code=400, detail="无法从URL中提取新闻文本")
        news_text = text
        original_url = request.url
        original_title = title
    else:
        news_text = request.text
    
    try:
        result = await process_news(news_text, original_url, original_title)
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