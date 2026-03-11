#整合流水线
from .claim_decomposer import decompose_claim
from .claim_verifier import verify_claim
from .evidence_retriever import EvidenceRetriever
from ..config import config
from typing import Dict, List, Optional
import difflib
import asyncio

retriever = EvidenceRetriever(config.BAIDU_API_KEY)#创建证据检索模块实例

def deduplicate_evidences(evidences, similarity_threshold=0.8) -> List[Dict]:
     """
     基于标题的去重，只保留第一个结果
     """
     if not evidences: return []

     unique = []

     for e in evidences:
          title = e.get("title", "")
          #如果为空，则使用 snippet 的前50个字符
          if not title: 
               title = e.get("snippet", "")[:50]

          #检查是否已经存在
          duplicate = False
          for u in unique:
               u_title = u.get("title", "")
               if not u_title: 
                    u_title = u.get("snippet", "")[:50]
               #计算相似度
               similarity = difflib.SequenceMatcher(None, title, u_title).ratio()
               if similarity >= similarity_threshold:
                    duplicate = True
                    break
               if not duplicate:
                    unique.append(e)
               else:
                    print(f"丢弃的证据: {title[:30]}")
     if not unique and evidences:
          print(f"所有都重复保留第一条")
          unique = [evidences[0]]
     return unique

async def process_single_claim(claim: str, original_url: Optional[str] = None, original_title: Optional[str] = None) -> Dict:
     """
     处理单个claim
     检索，去重，验证
     """
     loop = asyncio.get_event_loop()
     #异步检索
     evidences = await retriever.search(claim, original_url, original_title)
     #去重
     before_dedup = len(evidences)
     evidences = deduplicate_evidences(evidences, similarity_threshold=0.8)
     print(f"去重后证据数量: {len(evidences)} (去除了 {before_dedup - len(evidences)} 条)")

     #验证
     verdict = await loop.run_in_executor(
          None,
          verify_claim,
          claim,
          evidences
     )

     return{
          "claim": claim,
          "verdict": verdict.get("verdict","未知"),
          "confidence": verdict.get("confidence",0),
          "reason": verdict.get("reason",""),
          "evidences": evidences[:3],
     }
async def process_news(news_text: str, original_url: Optional[str] = None, original_title: Optional[str] = None) -> Dict:
     """
    完整的新闻处理流水线
    """
     #1.分解
     claims = decompose_claim(news_text)
     if not claims:
          return {
               "claims": [],
               "claims_count": 0,
               "overall_score": 0,
          }
     #2.并发执行
     tasks = [process_single_claim(claim, original_url, original_title) for claim in claims]
     results = await asyncio.gather(*tasks)

     #3.计算可信度
     total_weight = 0.0
     weighted_sum = 0.0
     for r in results:
          # 计算总权重
          weight = r["confidence"] / 100.0
          weighted_sum += r["confidence"] * weight
          total_weight += weight
     overall_score = weighted_sum / total_weight if total_weight > 0 else 0
   
     return {
          "overall_score": round(overall_score, 1),
          "claims": results,
          "claims_count": len(results),
     }