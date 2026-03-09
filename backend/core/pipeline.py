#整合流水线
from .claim_decomposer import decompose_claim
from .claim_verifier import verify_claim
from .evidence_retriever import search_evidence
from ..config import config
from typing import Dict
import difflib
import asyncio

def deduplicate_evidences(evidences, similarity_threshold=0.8):
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

async def process_news(news_text: str) -> Dict:
     """
    完整的新闻处理流水线
    """
     #1.分解
     claims = decompose_claim(news_text)

     #2.验证(异步验证)
     async def process_single_claim(claim: str) -> Dict:
          loop = asyncio.get_event_loop()
          evidences = await loop.run_in_executor(
               None, search_evidence, claim, config.BAIDU_API_KEY
          )
          #去重
          before_dedup = len(evidences)
          evidences = deduplicate_evidences(evidences, similarity_threshold=0.8)
          print(f"去重后证据数量: {len(evidences)} (去除了 {before_dedup - len(evidences)} 条)")

          #验证
          verdict = await loop.run_in_executor(
               None, verify_claim, claim, evidences
          )

          return{
               "claim": claim,
               "verdict": verdict.get("verdict","未知"),
               "confidence": verdict.get("confidence",0),
               "reason": verdict.get("reason",""),
               "evidences": evidences[:3],
          }

     #并发执行
     tasks = [process_single_claim(claim) for claim in claims]
     results = await asyncio.gather(*tasks)

     #3.计算可信度
     confidence_scores = [r["confidence"] for r in results if isinstance(r["confidence"],(int,float))]
     overall_score = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0

     return {
          "overall_score": overall_score,
          "claims": results,
          "claims_count": len(results),
     }