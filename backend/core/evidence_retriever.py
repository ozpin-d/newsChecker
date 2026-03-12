#证据检索
import requests
import time
import hashlib
import threading
import asyncio
import logging
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, HTTPError
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

#限流信号量（控制对百度API的并发）
_search_semaphore = asyncio.Semaphore(3)

#自定义异常
class QuotaExceededError(Exception):
    """百度API配额用完"""
    pass

class EvidenceRetriever:
    def __init__(self,api_key: str):
        """初始化，需要提供API KEY"""
        if not api_key:
            raise ValueError("API KEY is null")
        self.api_key = api_key
        self._cache = {} #缓存结构：{key:(timestamp,evidences)}
        self._cache_lock = threading.RLock() #重入锁
        self._session = self._create_session() #创建session
        self.cache_ttl = 600 #缓存有效期10分钟
        self.max_cache_size = 1000 #缓存大小限制

    def _create_session(self) -> requests.Session:
        """创建带认证头、重试策略和连接池的 Session"""
        session = requests.Session()
        #重试策略
        retries = Retry(
            total=3, #重试次数
            backoff_factor=1, #每次重试等待的时间间隔,使用指数退避算法，等待时间会随重试次数指数级增长
            status_forcelist=[429,500,502,503,504], #HTTP状态码
            allowed_methods=["POST"], #允许的HTTP方法
            raise_on_status=False #是否抛出异常
        )
        #创建适配器
        adapter = HTTPAdapter(
            max_retries=retries, #重试策略
            pool_connections=10, #连接池大小
            pool_maxsize=20, #最大连接数
        )
        #添加适配器
        session.mount('https://', adapter)
        session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        })
        return session
    async def search(self, claim: str, original_url: Optional[str] = None, original_title: Optional[str] = None) -> List[Dict]:
        """异步检索证据，全局限流"""
        async with _search_semaphore:
            # 在限流里面执行同步请求
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._sync_search, claim, original_url, original_title
            )

    def _sync_search(self, claim: str, original_url: Optional[str], original_title: Optional[str]) -> List[Dict]:
        """同步检索证据(带换缓存)"""
        cache_key = self._make_cache_key(claim)

        #尝试从缓存中调取数据
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached
        
        evidences = self._call_baidu_api(claim) #调用百度API

        if original_url and original_title: #过滤同源证据
            evidences = self._filter_self_sources(evidences, original_url, original_title)
        
        self._set_cache(cache_key, evidences) #缓存数据原子化操作

        return evidences
    
    def _call_baidu_api(self, claim: str) -> List[Dict]:
        """
        API调用， 使用连接池
        返回规范化后的证据列表，或在无法恢复的错误时抛出特定异常。

        错误处理策略：
        - 429 Too Many Requests：进一步区分：
            - QUOTA_USER_DAILY_FREE：免费额度用尽，需开通后付费
            - QUOTA_USER_DAILY_REQUEST：日配额用尽，需申请扩容
            - BILLING_INSUFFICIENT_BALANCE：账户欠费，需充值
            - 其他429（RATE_LIMIT_*）：QPS超限，重试即可
        - 5xx 服务器错误：抛出原始异常，触发重试。
        - 4xx 客户端错误（除 429 外）：记录错误并返回空列表，表示无法检索到证据。
        - 网络连接错误：抛出原始异常，触发重试。
        """
        url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
        payload  = {
            "messages": [{"content": claim[:72], "role": "user"}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": 10}],
        }

        
        try:
            # 发送POST请求
            resp = self._session.post(url,json=payload, timeout=15)
            resp.raise_for_status()
        except HTTPError as e:
            #处理HTTP错误状态码
            status_code = e.response.status_code
            error_detail = self._parse_error_response(e.response)
            error_code = self._extract_error_code(e.response) #获取错误码返回的是字符串

            if status_code == 429:
                #区分配额问题和QPS限流
                if error_code in ["QUOTA_USER_DAILY_FREE", "QUOTA_USER_DAILY_REQUEST", "BILLING_INSUFFICIENT_BALANCE"]:
                    #配额计费问题
                    error_type = {
                        "QUOTA_USER_DAILY_FREE": "免费额度用尽（需开通后付费）",
                        "QUOTA_USER_DAILY_REQUEST": "日配额用尽（需申请扩容）",
                        "BILLING_INSUFFICIENT_BALANCE": "账户欠费（需充值）"
                    }.get(error_code, "配额异常")

                    logger.error(f"百度搜索API{error_type}。错误码：{error_code}，详情：{error_detail}")
                    raise QuotaExceededError(f"{error_type}: {error_detail}") from e
                else:
                    #QPS超限,记录并让重试机制处理 
                    logger.warning(f"百度搜索API请求限流({error_code})，正在重试...详情{error_detail}")
                    raise # 重新抛出，让Session的重试机制处理
            elif 500 <= status_code < 600:
                logger.warning(f"百度搜索API请求失败({status_code})，正在重试...详情{error_detail}")
                raise
            else:
                logger.error(f"百度搜索API请求失败({status_code})，请检查API密钥和网络连接，详情{error_detail}")
                return []
        except RequestException as e:
            logger.error(f"百度搜索API请求失败，请检查API密钥和网络连接，详情{e}")
            raise

        try:
            data = resp.json()
            evidences = []
            for ref in data.get("references", []):
                if ref.get("type") == "web":
                    evidences.append({
                        "title": ref.get("title"),
                        "url": ref.get("url"),
                        "content": ref.get("content"),
                        "similarity": ref.get("similarity"),
                        "type": ref.get("type"),
                    })
            return evidences
        except ValueError as e:
            #JSON 解析错误
            logger.error(f"API返回非JSON: {e}")
            return []
        
    def _parse_error_response(self, response: requests.Response) -> str:
        """从错误响应中国提取刻度的错误消息，失败返回状态码"""
        try:
            error_data = response.json()
            return error_data.get("error", {}).get("massage", response.text)
        except:
            return response.text
    
    def _extract_error_code(self, response: requests.Response) -> Optional[str]:
        """从错误响应中提取错误代码"""
        try:
            error_data = response.json()
            #尝试多种可能的字段名
            return error_data.get("code") or error_data.get("error_code") or error_data.get("error", {}).get("code")
        except:
            return None
    
    def _filter_self_sources(self, evidences: List[Dict], original_url: str, original_title: str) -> List[Dict]:
        """过滤同源新闻"""
        from urllib.parse import urlparse
        import difflib

        filtered = []
        original_domain = urlparse(original_url).netloc if original_url else None 

        for e in evidences:
            link = e.get('link', '')
            domain = urlparse(link).netloc if link else None

            #域名排除
            if domain and original_domain and domain == original_domain:
                continue

            #标题排除
            title = e.get('title', '')
            if title and original_title:
                sim = difflib.SequenceMatcher(None, title, original_title).ratio()
                if sim > 0.7:
                    continue
            filtered.append(e)
        return filtered
    
    def _make_cache_key(self, claim: str) -> str:
        """缓存key,使用hashlib加速"""
        return hashlib.md5(claim.encode('utf-8')).hexdigest()
    
    def _get_from_cache(self, key: str) -> Optional[List[Dict]]:
        """获取缓存"""
        with self._cache_lock:
            if key in self._cache:
                timestamp, evidences = self._cache[key]
                if time.time() - timestamp < self.cache_ttl:
                    #深拷贝，防止篡改
                    return [e.copy() for e in evidences]
                else:
                    del self._cache[key]
        return None
    
    def _set_cache(self, key: str, evidences: List[Dict]):
        """设置缓存"""
        with self._cache_lock:
            #如果超限，删除最旧的10% LRU算法
            if len(self._cache) >= self.max_cache_size:
                #按时间戳排序
                items = sorted(self._cache.items(), key=lambda x: x[1][0])
                for old_key, _ in items[:max(1, len(self._cache)//10)]:
                    del self._cache[old_key]
            self._cache[key] = (time.time(), evidences)
        
# #缓存结构：{key:(timestamp,evidences)}
# _cache = {}
# _cache_lock = threading.Lock()
# CACHE_TTL = 600

# def _make_cache_key(claim: str) -> str:
#     """根据主张生成缓存键（MD5哈希）"""
#     return hashlib.md5(claim.encode('utf-8')).hexdigest()

# def search_evidence(claim: str, api_key: str) -> List[Dict]:
#     """
#     使用百度AI搜索API检索证据
#     官方文档：https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5
#     """

#     key = _make_cache_key(claim)

#     with _cache_lock:
#         #检查缓存
#         if key in _cache:
#             timestamp, evidences = _cache[key]
#             if time.time() - timestamp < CACHE_TTL: #时间没到
#                 print("从缓存中获取数据")
#                 return [e.copy() for e in evidences]
#             else:
#                 print("缓存已过期，重新搜索")
#     print(f"正在为主张检索证据：{claim[:50]}...")
#     #如果没传入api_key则使用config中的
#     if api_key is None:
#         api_key = config.BAIDU_API_KEY
    
#     if not api_key:
#         print("请传入百度API Key")
#         return []
    
#     try:
#         url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
        
#         #请求参数
#         playload = {
#             "messages": [
#                 {
#                     "role": "user",
#                     "content": claim[:72] #百度限制72个字符[citation:3]
#                 }
#             ],
#             "search_source":"baidu_search_v2",
#             "resource_type_filter":[
#                 {"type":"web", "top_k":10} #百度搜索结果数量10个网页
#             ]
#         }

#         headers = {#网站头部
#             "Content-Type": "application/json",
#             "Authorization": f"Bearer {api_key}"
#         }

#         response = requests.post(url, json=playload, headers=headers, timeout=15)
#         response.raise_for_status()

#         data = response.json()

#         #提取结果
#         evidences = []

#         #百度返回的结果在references中
#         references = data.get("references", [])
#         for ref in references:
#             #只取网页类型的结果
#             if ref.get("type") == "web":
#                 evidences.append({
#                     "title": ref.get("title",""),
#                     "snippet": ref.get("content", "") or ref.get("snippet",""),
#                     "link": ref.get("url", ""),
#                     "source": ref.get("website", ""),
#                     "date": ref.get("date", ""),
#                     "authority_score": ref.get("authority_score", 0)#百度提供的权威性评分
#                 })
#         print(f"检索到{len(evidences)}条证据")

#         #存入缓存
#         with _cache_lock:
#             _cache[key] = (time.time(), evidences)
        
#         return evidences
#     except Exception as e:
#         print(f"搜索失败: {e}")
#         import traceback
#         traceback.print_exc()
#         return []