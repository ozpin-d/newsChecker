#在URL里面提取文本
import requests
import logging
from bs4 import BeautifulSoup
from newspaper import Article, Config as NewspaperConfig
from typing import Tuple, Optional
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class URLExtractor:
    """
    线程安全的URL提取器，支持newspaper3k和BeautifulSoup两种方式。
    内部维护requests.Session实现连接复用和重试。
    """
    def __init__(self, timeout: int = 15, max_retries: int = 2, pool_connections: int = 10):
        """初始化URL提取器"""
        self.timeout = timeout #超时时间
        self.max_retries = max_retries #最大重试次数

        #备用方法使用rrequests.Session实现连接复用和重试
        self._session = requests.Session()

        #重试策略
        retries = Retry(
            total=max_retries, #最大重试次数
            backoff_factor=0.5, #等待时间间隔,使用指数退避算法，等待时间会随重试次数指数级增长
            status_forcelist=[500,502,503,504], #HTTP状态码 
            allowed_methods=["GET"], #允许的HTTP方法
            raise_on_status=False #是否抛出异常
        )

        #创建适配器
        adapter = HTTPAdapter(
            pool_connection=pool_connections,
            pool_maxsize=pool_connections * 2,
            max_retries=retries,
        )
        self._session.mount('https://', adapter)
        self._session.mount('http://', adapter)

        #session头,降低被反爬的概率
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36',
            'Accept': 'zh-CN,zh;q=0.9',
        })

        #newspaper3k配置
        self._newspaper_config = NewspaperConfig()
        self._newspaper_config.browser_user_agent = self.session.headers['User-Agent']
        self._newspaper_config.request_timeout = timeout
        self._newspaper_config.memoize_articles = False #禁用缓存
        self._newspaper_config.fetch_images = False #禁用图片下载

    def _validate_url(self, url: str) -> bool:
        """验证URL,防SSRF，只允许http和https"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except Exception:
            return False
        
    def extract(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从给定的 URL 提取新闻标题和正文。
        优先使用 newspaper3k，若失败或结果为空则回退到 BeautifulSoup 手动提取。
        返回 (title, text) 元组，若完全失败则返回 (None, None)。

        :param url: 新闻页面的完整 URL
        :return: (标题, 正文) 或 (None, None)
        """
        #安全检查
        if not self._validate_url(url):
             logger.error(f"Invalid URL: {url[:50]}")
             return None, None
        #使用 newspaper3k
        try:
            title, text = self._extract_with_newspaper(url)
            if title and text:
                logger.info(f"提取成功：{url[:50]}")
                return title, text
            logger.debug(f"提取失败,planB：{url[:50]}")
        except Exception as e:
            logger.warning(f"planB失败：{e}", exc_info=True)
        
        #备用方法requests + bs4
        try:
            title, text = self._extract_with_bs4(url)
            if title and text:
                logger.info(f"planB成功：{url[:50]}")
                return title, text
            logger.error(f"planB提取失败：{url[:50]}")
            return None,None
        except Exception as e:
            logger.warning(f"planB失败：{e}", exc_info=True)
            return None,None
        
    def _extract_with_newspaper(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        使用newspaper3k进行网页内容提取
        """
        article = Article(url, config=self._newspaper_config, language='zh')
        article.download()
        article.parse()
        title = article.title.strip() if article.title else None
        text = article.text.strip() if article.text else None
        return title, text
    
    def _extract_with_bs4(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        使用BeautifulSoup进行网页内容提取（planB）
        """
        resp = self._session.get(url, timeout=self.timeout)
        resp.encoding = "utf-8"
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')

        title = None
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
        if not title:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()

        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            try:
                tag.decompose()
            except AttributeError:
                tag.extract()

        #去除空白格式化
        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines) if lines else None

        return title, text
    
    def close(self):
        """关闭会话"""
        self._session.close()

    def _enter_(self):
        """进入上下文"""
        return self
    
    def _exit_(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        self.close()


default_extractor = URLExtractor()
# def extract_from_url(url: str) -> str:
#     """从URL中提取新闻标题和正文，返回(title, text) 元组。"""
#     try:
#         #先使用newspaper3k尝试
#         article = Article(url, language='zh')
#         article.download()
#         article.parse()
#         title = article.title
#         text = article.text
#         if title and text:
#             return title, text
        
#         #如果newspaper3k失败，则使用requests和BeautifulSoup
#         headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
#         response = requests.get(url, headers=headers, timeout=10)
#         response.encoding = 'utf-8'
#         soup = BeautifulSoup(response.text, 'html.parser')

#         #尝试提取标题
#         title_tag = soup.find('title')
#         title = title_tag.get_text() if title_tag else None

#         #移除脚本和样式标签
#         for script in soup(["script", "style"]):
#             script.decompose()

#         text = soup.get_text()
#         lines = (line.strip() for line in text.splitlines())
#         chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
#         text = ' '.join(chunk for chunk in chunks if chunk)
#         return text
#     except Exception as e:
#         print(f"提取失败: {e}")
#         return ""