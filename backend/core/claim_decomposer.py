#分解新闻主张
import openai
from typing import List
from ..config import config

#配置deepseek
client = openai.OpenAI(
    api_key=config.DEEPSEEKAPI_KEY,
    base_url=config.DEEPSEEK_BASE_URL
)

#提示词
def decompose_claim(news_text: str) -> List[str]:
    """
    将新闻文本分解为可验证的原子主张
    参考Loki的Decomposer设计[citation:7]
    """
    prompt = f"""
    你是一个专业的事实核查助手。请将以下新闻文本分解成若干个独立的、可验证的原子主张。
    要求：
    1. 每个主张应该是具体的事实陈述，而非观点或推测
    2. 输出格式：以JSON数组形式返回，每个元素是一个字符串
    3. 只返回JSON，不要有其他解释

    新闻文本：
    {news_text}
    """
    try: 
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODULE,
            messages=[
                {"role": "system", "content": "你是一个专业的事实核查助手，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1, #降低随机性
            response_format={"type": "json_object"} #deepseek要求返回JSON
        )

        print(f"response 类型: {type(response)}")
        print(f"response.choices 类型: {type(response.choices)}")

        if not response.choices or not isinstance(response.choices, list):
            print("choices 为空或无效")
            return []
        
        message_content = response.choices[0].message.content

        print(f"message.content 类型: {type(message_content)}")
        print(f"message.content 预览: {message_content[:200]}")

        import json
        result = json.loads(message_content)
        print(f"解析后的 result 类型: {type(result)}")
        print(f"result 内容预览: {str(result)[:200]}")

        #如果是字典
        if isinstance(result, dict):
            claims = result.get("claims", [])
        #如果是列表
        elif isinstance(result, list):
            claims = result
        else:
            print(f"无法解析结果 返回的类型为{type(result)}")
            return []
        
        # 确保 claims 是列表
        if isinstance(claims, list):
            return claims
        else:
            print("警告：claims 不是列表，返回空")
            return []
    except Exception as e:
        print(f"分解失败: {e}")
        import traceback
        traceback.print_exc()
        return []