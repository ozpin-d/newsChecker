#评估处理
import json
import logging
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError
from typing import List, Dict, Optional
from ..config import config

logger = logging.getLogger(__name__)

_client = None

def _get_client() -> OpenAI:
    """初始化DeepSeek客户端，确保不会重复创建"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.DEEPSEEKAPI_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )
    return _client

def verify_claim(claim: str, evidences: List[Dict]) -> Dict:
    """
    基于证据验证主张的真实性
    输出：支持/反对/存疑 + 置信度 + 理由

    :param claim: 原子主张字符串
    :param evidences: 证据列表，每个证据应包含 title, snippet, link, source, authority_score 等字段
    :return: 包含 verdict, confidence, reason, key_evidence 的字典，失败时返回默认值
    """
    if not claim:
        logger.warning("主张为空，跳过验证")
        return _defalt_verdict ("主张为空", "证据不足", 0)
    
    if not evidences:
        logger.info(f"主张:{claim[:50]}无证据，返回空")
        return _defalt_verdict ("未检索到相关证据", "证据不足", 0)

    #按照权威性进行排序
    sorted_evidences = sorted(
        evidences,
        key=lambda x: x.get("authority_source", 0),
        reverse=True,
    )
    top_evidences = sorted_evidences[:5]

    #构建证据文本
    evidences_lines = []
    for i, e in enumerate(top_evidences, 1):
        source = e.get("source", "未知来源")
        title = e.get("title", "无标题")
        snippet = e.get("snippet", "")[:200]
        link = e.get("link", "")
        authority = e.get("authority_score", 0)
        evidences_lines.append(
            f"证据{i} [{source} 权威性：{authority}]\n"
            f"标题: {title}\n"
            f"摘要: {snippet}\n"
            f"链接: {link}\n"
        )
    evidence_text = "\n\n".join(evidences_lines)

    system_msg = "你是一个专业事实核查员。请基于提供的证据，验证以下主张的真实性。\n权威性评分越高，证据越可靠。"
    user_msg = (
        f"主张：{claim}\n\n"
        f"检索到的证据（按权威性从高到低排序）：\n{evidence_text}\n\n"
        "请输出JSON格式的评估结果，包含：\n"
        "- verdict: 取值 \"支持\"、\"反对\"、\"存疑\"、\"证据不足\"\n"
        "- confidence: 0-100的置信度分数\n"
        "- reason: 简要理由\n"
        "- key_evidence: 关键证据的链接列表\n"
        "只返回JSON，不要有其他内容。\n"
    )

    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODULE,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1, #降低随机性
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        logger.debug(f"Verify API start: {content[:200]}...")

        result = json.loads(content)
        verdict = result.get("verdict", "证据不足")
        confidence = result.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 100):
            confidence = 0
        reason = result.get("reason", "")
        key_evidence = result.get("key_evidence", [])
        if not isinstance(key_evidence, list):
            key_evidence = []

        logger.info(f"主张验证完成：{verdict} ({confidence}%)")
        return {
            "verdict": verdict,
            "confidence": int(confidence),
            "reason": reason,
            "key_evidence": key_evidence,
        }
    
    except json.JSONDecodeError as e:
        logger.error(f"验证响应JSON解析失败：{e}, 原始内容： {content[:200]}")
        return _defalt_verdict ("API返回非JSON格式", "验证失败", 0)
    except RateLimitError as e:
        logger.warning(f"Deepseek限流: {e}")
        raise
    except APIConnectionError as e:
        logger.error(f"DeepSeek API 连接失败: {e}")
        raise
    except APIStatusError as e:
        logger.error(f"API 状态错误: {e.status_code}: {e.response}")
        if 400 <= e.status_code < 500:
            return _defalt_verdict (f"客户端错误 {e.status_code}", "验证失败", 0)
        raise
    except Exception as e:
        logger.exception(f"未知错误：{e}")
        return _defalt_verdict ("未知错误", "验证失败", 0)
    
def _defalt_verdict(reason: str, verdict: str = "验证失败", confidence: int = 0) -> Dict:
    """默认的验证结果"""
    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "key_evidence": [],
    }
# client = openai.OpenAI(
#     api_key=config.DEEPSEEKAPI_KEY,
#     base_url=config.DEEPSEEK_BASE_URL
#     )
# def verify_claim(claim: str, evidences: List[Dict]) -> Dict:
#     """
#     基于证据验证主张的真实性
#     输出：支持/反对/存疑 + 置信度 + 理由
#     """
#     #对证据按权威性进行排序
#     sorted_evidences = sorted(
#         evidences,
#         key=lambda x: x.get('authority_source', 0),
#         reverse=True,
#     )

#     #取前5条高权威证据用于验证
#     top_evidences = sorted_evidences[:5]

#     # 将证据拼接成文本,强调权威性和证据来源
#     evidence_text = "\n\n".join([
#         f"来源{i+1}：{e['source']}（权威性评分：{e['authority_score']}）\n标题：{e['title']}\n摘要：{e['snippet']}\n链接：{e['link']}"
#         for i, e in enumerate(top_evidences)
#     ])

#     #提示词
#     prompt = f"""
#     你是一个专业的事实核查员。请基于提供的证据，验证以下主张的真实性。
#     权威性评分越高，证据越可靠。

#     主张：{claim}

#     检索到的证据：
#     {evidence_text}

#     请输出JSON格式的评估结果，包含：
#     - verdict: 取值 "支持"、"反对"、"存疑"、"证据不足"
#     - confidence: 0-100的置信度分数
#     - reason: 简要理由
#     - key_evidence: 关键证据的链接列表

#     只返回JSON，不要有其他内容。
#     """
    
#     try: 
#         response = client.chat.completions.create(
#             model=config.DEEPSEEK_MODULE,
#             messages=[
#                 {"role": "system", "content": "你是一个专业的事实核查员"},
#                 {"role": "user", "content": prompt},
#             ],
#             temperature=0.1, #降低随机性
#             response_format={"type": "json_object"}
#         )

#         import json
#         result = json.loads(response.choices[0].message.content)
#         if isinstance(result, dict): #防止API返回非JSON
#             return result
#         elif isinstance(result, str):
#             #如果返回了列表尝试重新包装
#             return {
#                 "verdict": "格式错误",
#                 "confidence": 0,
#                 "reason": f"API返回错误：{str(e)}",
#                 "key_evidence": []
#             }
#     except Exception as e:
#         print(f"主张验证失败: {e}")
#         import traceback
#         traceback.print_exc()
#         return {
#             "verdict": "无法评估",
#             "confidence": 0,
#             "reason": f"API错误：{str(e)}",
#             "key_evidence": []
#         }
