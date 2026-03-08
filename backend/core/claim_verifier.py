#评估处理
import openai
from typing import List, Dict
from ..config import config

client = openai.OpenAI(
    api_key=config.DEEPSEEKAPI_KEY,
    base_url=config.DEEPSEEK_BASE_URL
    )
def verify_claim(claim: str, evidences: List[Dict]) -> Dict:
    """
    基于证据验证主张的真实性
    输出：支持/反对/存疑 + 置信度 + 理由
    """
    # 将证据拼接成文本
    evidence_text = "\n\n".join([
        f"来源{i+1}:{e['title']}\n摘要：{e['snippet']}\n链接：{e['link']}"
        for i, e in enumerate(evidences)
    ])

    #提示词
    prompt = f"""
你是一个专业的事实核查员。请基于提供的证据，验证以下主张的真实性。

主张：{claim}

检索到的证据：
{evidence_text}

请输出JSON格式的评估结果，包含：
- verdict: 取值 "支持"、"反对"、"存疑"、"证据不足"
- confidence: 0-100的置信度分数
- reason: 简要理由
- key_evidence: 关键证据的链接列表

只返回JSON，不要有其他内容。
"""
    
    try: 
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODULE,
            messages=[
                {"role": "system", "content": "你是一个专业的事实核查员"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1, #降低随机性
            response_format={"type": "json_object"}
        )

        import json
        result = json.loads(response.choices[0].message.content)
        if isinstance(result, dict): #防止API返回非JSON
            return result
        elif isinstance(result, str):
            #如果返回了列表尝试重新包装
            return {
                "verdict": "格式错误",
                "confidence": 0,
                "reason": f"API返回错误：{str(e)}",
                "key_evidence": []
            }
    except Exception as e:
        print(f"主张验证失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "verdict": "无法评估",
            "confidence": 0,
            "reason": f"API错误：{str(e)}",
            "key_evidence": []
        }
