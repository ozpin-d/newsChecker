#分解新闻主张
import logging
import json 
import tiktoken
from openai import OpenAI, APIConnectionError, RateLimitError, APIStatusError
from typing import List, Optional
from ..config import config

#日志
logger = logging.getLogger(__name__)

#初始化客户端deepseek
_client = None

def _get_client() -> OpenAI:
    """初始化DeepSeek客户端，确保不会重复创建"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key = config.DEEPSEEKAPI_KEY,
            base_url = config.DEEPSEEK_BASE_URL
        )

    return _client

#上下文限制
MAX_INPUT_TOKENS = 8000

#使用tiktoken计算输入的token数
_ENCODING = tiktoken.get_encoding("cl100k_base")

def _truncate_text(text: str, max_tokens: int = MAX_INPUT_TOKENS) -> str:
    """
    将文本截断到最大 token 数，优先保留开头部分（新闻关键信息通常在开头）。
    """
    try:
        tokens = _ENCODING.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens] #截断
        return _ENCODING.decode(truncated_tokens)
    except Exception as e:
        logger.warning(f"截断失败：{e},启用B计划")
        approx_max_tokens = int(max_tokens * 1.3)
        return text[:approx_max_tokens]
    
def decompose_claim(news_text: str, max_claims: int = 10) -> List[str]:
    """
    将新闻文本分解为可验证的原子主张
    参考Loki的Decomposer设计[citation:7]

    :param news_text: 新闻文本
    :param max_claims: 最大返回的主张数量
    :return: 主张列表（可能为空）
    """
    if not news_text or not news_text.strip():
        logger.warning("新闻文本为空，无法分解")
        return []
    
    truncated_text = _truncate_text(news_text)

    system_msg = """你是一个专业的事实核查助手，请将用户的新闻文本分解成独立的、**可验证的客观事实主张**。
    避免提取主观观点、猜测或人物心理。
    如果原文包含“某人声称/怀疑/认为某事”，请同时提取两个主张：
    (1) 某人确实说了/做了某事（事实性）；
    (2) 某事本身是否正确（客观事实）。
    要求：
    1. 每个主张应该是具体的事实陈述，而非观点或推测
    2. 输出格式：以JSON数组形式返回，每个元素是一个字符串
    3. 只返回JSON，不要有其他解释
    """
    user_msg = f"新闻文本：\n{truncated_text}\n\n请输出 JSON，格式：{{\"claims\": [\"主张1\", \"主张2\", ...]}}，最多 {max_claims} 条。"

    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODULE,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.1, #降低随机性
            max_tokens=5000, #最大输出长度
            response_format={"type": "json_object"} #deepseek要求返回JSON
        )
        content = response.choices[0].message.content
        logger.debug(f"Decompose API start: {content[:200]}...")

        result = json.loads(content)
        claims = result.get("claims", [])
        if not isinstance(claims, list):
            logger.error(f"API返回的不是列表: {type(claims)}")
            return []
        
        claims = [c.strip() for c in claims if c and isinstance(c, str)]
        claims = claims[:max_claims]
        logger.info(f"分解成功，分解数量：{len(claims)}")
        return claims
    
    except json.JSONDecodeError as e:
        logger.error(f"json 解析失败: {e},原始响应：{content[:200]}")
        return []
    except RateLimitError as e:
        logger.warning(f"DeepSeek API 限流: {e}")
        raise 
    except APIConnectionError as e:
        logger.warning(f"DeepSeek API 连接失败: {e}")
        raise 
    except APIStatusError as e:
        logger.error(f"API 状态错误 {e.status_code}: {e.response}")
        if 400 <= e.status_code < 500:
            return []
        raise
    except Exception as e:
        logger.exception(f"未知错误")
        return []
# #配置deepseek
# client = openai.OpenAI(
#     api_key=config.DEEPSEEKAPI_KEY,
#     base_url=config.DEEPSEEK_BASE_URL
# )

# #提示词
# def decompose_claim(news_text: str) -> List[str]:
#     """
#     将新闻文本分解为可验证的原子主张
#     参考Loki的Decomposer设计[citation:7]
#     """
#     prompt = f"""
#     你是一个专业的事实核查助手。请将以下新闻文本分解成若干个独立的、可验证的原子主张。
#     要求：
#     1. 每个主张应该是具体的事实陈述，而非观点或推测
#     2. 输出格式：以JSON数组形式返回，每个元素是一个字符串
#     3. 只返回JSON，不要有其他解释

#     新闻文本：
#     {news_text}
#     """
#     try: 
#         response = client.chat.completions.create(
#             model=config.DEEPSEEK_MODULE,
#             messages=[
#                 {"role": "system", "content": "你是一个专业的事实核查助手，只输出 JSON。"},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.1, #降低随机性
#             response_format={"type": "json_object"} #deepseek要求返回JSON
#         )

#         print(f"response 类型: {type(response)}")
#         print(f"response.choices 类型: {type(response.choices)}")

#         if not response.choices or not isinstance(response.choices, list):
#             print("choices 为空或无效")
#             return []
        
#         message_content = response.choices[0].message.content

#         print(f"message.content 类型: {type(message_content)}")
#         print(f"message.content 预览: {message_content[:200]}")

#         import json
#         result = json.loads(message_content)
#         print(f"解析后的 result 类型: {type(result)}")
#         print(f"result 内容预览: {str(result)[:200]}")

#         #如果是字典
#         if isinstance(result, dict):
#             claims = result.get("claims", [])
#         #如果是列表
#         elif isinstance(result, list):
#             claims = result
#         else:
#             print(f"无法解析结果 返回的类型为{type(result)}")
#             return []
        
#         # 确保 claims 是列表
#         if isinstance(claims, list):
#             return claims
#         else:
#             print("警告：claims 不是列表，返回空")
#             return []
#     except Exception as e:
#         print(f"分解失败: {e}")
#         import traceback
#         traceback.print_exc()
#         return []