import streamlit as st
import requests

st.set_page_config(page_title="新闻可信度检测器", page_icon="🔍", layout="wide")

API_URL = "http://localhost:8000/api/v1"

st.title("🔍 新闻可信度检测器")
st.markdown("输入新闻文本或URL，AI将自动检索全网信息并评估可信度")

with st.sidebar:
    st.header("关于")
    st.info("这是一个开源的事实核查工具，基于AI技术帮助您判断新闻可信度。")
    st.markdown("---")
    st.caption("⚠️ 结果仅供参考，请结合多方信息判断")

input_type = st.radio("选择输入方式", ["直接粘贴文本", "输入URL"], horizontal=True)

news_text = ""
url = ""

if input_type == "直接粘贴文本":
    news_text = st.text_area("粘贴新闻文本", height=200, placeholder="请粘贴新闻内容...")
else:
    url = st.text_input("输入新闻URL", placeholder="https://...")

if st.button("开始检测", type="primary", use_container_width=True):
    if input_type == "直接粘贴文本" and not news_text:
        st.warning("请输入新闻内容")
    elif input_type == "输入URL" and not url:
        st.warning("请输入URL")
    else:
        with st.spinner("正在分析，可能需要30-60秒..."):
            try:
                payload = {"text": news_text, "url": url}
                response = requests.post(f"{API_URL}/check", json=payload, timeout=120)
                
                if response.status_code == 200:
                    result = response.json()["data"]
                    st.success("分析完成！")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        score = result["overall_score"]
                        if score >= 80:
                            desc = "高度可信"
                        elif score >= 60:
                            desc = "基本可信"
                        elif score >= 40:
                            desc = "部分存疑"
                        else:
                            desc = "不可信"
                        st.metric("整体可信度", f"{score}%", delta=desc)
                    
                    st.subheader("主张明细")
                    for claim in result["claims"]:
                        with st.expander(f"{claim['claim'][:50]}... - {claim['verdict']} ({claim['confidence']}%)"):
                            st.write(f"理由：{claim['reason']}")
                            if claim['evidences']:
                                st.write("证据来源：")
                                for e in claim['evidences']:  # 修改这里
                                    title = e.get('title', '无标题')
                                    link = e.get('link', '#')
                                    st.write(f"- [{title}]({link})")
                            else:
                                st.write("无相关证据")
            except Exception as e:
                st.error(f"请求失败：{str(e)}")