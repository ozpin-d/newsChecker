#整合流水线
from .claim_decomposer import decompose_claim
from .claim_verifier import verify_claim
from .evidence_retriever import EvidenceRetriever, QuotaExceededError
from ..config import config
from typing import Dict, List, Optional
import logging
import difflib
import asyncio

logger = logging.getLogger(__name__)

retriever = EvidenceRetriever(config.BAIDU_API_KEY)#创建证据检索模块实例

def deduplicate_evidences(evidences: List[Dict], similarity_threshold=0.8) -> List[Dict]:
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

async def process_single_claim(
     claim: str, 
     original_url: Optional[str] = None, 
     original_title: Optional[str] = None
) -> Dict:
     """
     处理单个claim
     检索，去重，验证
     """
     loop = asyncio.get_event_loop()
     #异步检索
     try:
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
     except QuotaExceededError as e:
          error_msg=f"百度配额用完，无法检索: {e}"
          print(error_msg)
          return{
               "claim": claim,
               "verdict": "配额不足",
               "confidence": 0,
               "reason": error_msg,
               "evidences": [],
          }
     except asyncio.CancelledError:
          raise
     except Exception as e:
          error_msg = f"处理该主张时发生错误: {type(e).__name__}: {e}"
          print(error_msg)
          return{
               "claim": claim,
               "verdict": "处理失败",
               "confidence": 0,
               "reason": error_msg,
               "evidences": [],
          }
async def process_news(
     news_text: str, 
     original_url: Optional[str] = None, 
     original_title: Optional[str] = None
) -> Dict:
     """
    完整的新闻处理流水线
    """
     #1.分解
     claims_data = decompose_claim(news_text)
     if not claims_data:
          return {
               "claims": [],
               "claims_count": 0,
               "overall_score": 0,
               "overall_verdict": "无法判断",
               "note": "无法分解主张",
          }
     #2.并发执行
     tasks = [process_single_claim(c["text"], original_url, original_title) for c in claims_data]
     results = await asyncio.gather(*tasks, return_exceptions=False)

     #将重要结果合并到结果来里面
     for i, r in enumerate(results):
          r["importance"] = claims_data[i].get("importance", "medium")

     #3.计算可信度
     #优先计算反对主张的最高置信度
     oppose_confidences = [r["confidence"] for r in results if r["verdict"] == "反对"]
     max_oppose = max(oppose_confidences) / 100.0 if oppose_confidences else 0.0

     #计算支持主张的平均分
     support_confidences = [r["confidence"] for r in results if r["verdict"] == "支持"]
     avg_support = sum(support_confidences) / len(support_confidences) if support_confidences else 0.0

     #计算整体可信度
     if max_oppose > 0.7:
          overall_score = avg_support * (1-max_oppose)
     else:
          overall_score = avg_support if support_confidences else 0.0

     #4.判断核心主张（基于importance）
     core_verdict = None #核心内容结果

     #优先使用high主张
     for r in results:
          if r.get("importance", "") == "high":
               if r["verdict"] in ["反对", "证据不足"]:
                    core_verdict = "存疑" if r["verdict"] == "证据不足" else "不实"
                    logger.info(f"核心判断触发 (high): 主张 '{r['claim'][:30]}...' 判定为 {r['verdict']}")
                    break
               elif r["verdict"] == "支持" and r["confidence"] < 50:
                    core_verdict = "存疑"
                    logger.info(f"核心判断触发 (high): 主张 '{r['claim'][:30]}...' 支持但置信度过低")
                    break

     #如果没有high主张，使用medium
     if core_verdict is None:
          for r in results:
               if r.get("importance", "") == "medium":
                    if r["verdict"] in ["反对", "证据不足"]:
                         core_verdict = "存疑" if r["verdict"] == "证据不足" else "不实"
                         logger.info(f"核心判断触发 (medium): 主张 '{r['claim'][:30]}...' 判定为 {r['verdict']}")
                         break
                    elif r["verdict"] == "支持" and r["confidence"] < 50:
                         core_verdict = "存疑"
                         logger.info(f"核心判断触发 (medium): 主张 '{r['claim'][:30]}...' 支持但置信度过低")
                         break

     #如果还是没有就返回默认值
     if core_verdict is None:
          core_verdict = "存疑，无结果"
          logger.info("未触发核心判断，默认存疑")

     logger.debug(f"核心内容结果: {core_verdict}")
     overall_verdict = core_verdict
     
     # total_weight = 0.0
     # weighted_sum = 0.0
     # for r in results:
     #      # 计算总权重
     #      weight = r["confidence"] / 100.0
     #      weighted_sum += r["confidence"] * weight
     #      total_weight += weight
     # overall_score = weighted_sum / total_weight if total_weight > 0 else 0
   
     return {
          "overall_score": round(overall_score, 1),
          "overall_verdict": overall_verdict,
          "claims": results,
          "claims_count": len(results),
     }