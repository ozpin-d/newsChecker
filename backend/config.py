import os
from dotenv import load_dotenv

load_dotenv()#加载.env文件

class Config:
    DEEPSEEKAPI_KEY = os.getenv('DEEPSEEK_API_KEY')
    BAIDU_API_KEY = os.getenv("BAIDU_API_KEY")

    #API配置
    DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
    DEEPSEEK_MODULE = 'deepseek-chat'

    #搜索配置
    SEARCH_ENGINE = 'baidu'
    SEARCH_RESULT_COUNT = 5

    #缓存配置
    ENABLE_CACHE = True
    CACHE_DIR = 'data/cache'

config = Config()