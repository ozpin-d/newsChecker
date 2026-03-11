#在URL里面提取文本
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from typing import Tuple, Optional

def extract_from_url(url: str) -> str:
    """从URL中提取新闻标题和正文，返回(title, text) 元组。"""
    try:
        #先使用newspaper3k尝试
        article = Article(url, language='zh')
        article.download()
        article.parse()
        title = article.title
        text = article.text
        if title and text:
            return title, text
        
        #如果newspaper3k失败，则使用requests和BeautifulSoup
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')

        #尝试提取标题
        title_tag = soup.find('title')
        title = title_tag.get_text() if title_tag else None

        #移除脚本和样式标签
        for script in soup(["script", "style"]):
            script.decompose()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        return text
    except Exception as e:
        print(f"提取失败: {e}")
        return ""