#证据检索
import requests
from typing import List, Dict
from ..config import config
import time
import hashlib
import threading

#缓存结构：{key:(timestamp,evidences)}
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600

def _make_cache_key(claim: str) -> str:
    """根据主张生成缓存键（MD5哈希）"""
    return hashlib.md5(claim.encode('utf-8')).hexdigest()

def search_evidence(claim: str, api_key: str) -> List[Dict]:
    """
    使用百度AI搜索API检索证据
    官方文档：https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5
    """

    key = _make_cache_key(claim)

    with _cache_lock:
        #检查缓存
        if key in _cache:
            timestamp, evidences = _cache[key]
            if time.time() - timestamp < CACHE_TTL: #时间没到
                print("从缓存中获取数据")
                return [e.copy() for e in evidences]
            else:
                print("缓存已过期，重新搜索")
    print(f"正在为主张检索证据：{claim[:50]}...")
    #如果没传入api_key则使用config中的
    if api_key is None:
        api_key = config.BAIDU_API_KEY
    
    if not api_key:
        print("请传入百度API Key")
        return []
    
    try:
        url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
        
        #请求参数
        playload = {
            "messages": [
                {
                    "role": "user",
                    "content": claim[:72] #百度限制72个字符[citation:3]
                }
            ],
            "search_source":"baidu_search_v2",
            "resource_type_filter":[
                {"type":"web", "top_k":10} #百度搜索结果数量10个网页
            ]
        }

        headers = {#网站头部
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.post(url, json=playload, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()

        #提取结果
        evidences = []

        #百度返回的结果在references中
        references = data.get("references", [])
        for ref in references:
            #只取网页类型的结果
            if ref.get("type") == "web":
                evidences.append({
                    "title": ref.get("title",""),
                    "snippet": ref.get("content", "") or ref.get("snippet",""),
                    "link": ref.get("url", ""),
                    "source": ref.get("website", ""),
                    "date": ref.get("date", ""),
                    "authority_score": ref.get("authority_score", 0)#百度提供的权威性评分
                })
        print(f"检索到{len(evidences)}条证据")

        #存入缓存
        with _cache_lock:
            _cache[key] = (time.time(), evidences)
        
        return evidences
    except Exception as e:
        print(f"搜索失败: {e}")
        import traceback
        traceback.print_exc()
        return []
        