#整合流水线
from .claim_decomposer import decompose_claim
from .claim_verifier import verify_claim
from .evidence_retriever import search_evidence
from ..config import config
from typing import Dict

async def process_news(news_text: str) -> Dict:
     """
    完整的新闻处理流水线
    """
     #1.分解
     claims = decompose_claim(news_text)

     #2.验证
     results = []
     for claim in claims:
          #搜索证据
          evidences = search_evidence(claim, config.BAIDU_API_KEY)
          if not isinstance(evidences,list):
               evidences = []
          verdict = verify_claim(claim, evidences)

          results.append({
               "claim": claim,
               "verdict": verdict.get("verdict","未知"),
               "confidence": verdict.get("confidence",0),
               "reason": verdict.get("reason",""),
               "evidences": evidences[:3],
          })

     #3.计算可信度
     confidence_scores = [r["confidence"] for r in results if isinstance(r["confidence"],(int,float))]
     overall_score = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0

     return {
          "overall_score": overall_score,
          "claims": results,
          "claims_count": len(results),
     }