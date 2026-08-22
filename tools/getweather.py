import requests,re
from xpinyin import Pinyin


def parse_weather_simple(html_content):
    """
    使用正则表达式提取城市、天气、气温信息
    param: html_content 爬取的网页内容
    该工具从i.tianqi.com网页获取数据
    :return 城市、天气、气温 的json格式的字符串
    """
    # 提取城市
    city_match = re.search(r'<span[^>]*class="boild"[^>]*>([^<]+)</span>', html_content)
    city = city_match.group(1) if city_match else None
    
    # 提取天气（在wtmid flexr div中）
    weather_match = re.search(r'<div[^>]*class="wtmid flexr"[^>]*>.*?<img[^>]*>.*?([晴多云雨雪阴][^<]*)</div>', html_content, re.DOTALL)
    weather = weather_match.group(1).strip() if weather_match else None
    # 如果有&nbsp;等特殊字符，清理一下
    if weather:
        weather = re.sub(r'&nbsp;', ' ', weather).strip()
    
    # 提取气温
    temp_low_match = re.search(r'<span[^>]*class="cc30"[^>]*>([^<]+)</span>', html_content)
    temp_high_match = re.search(r'<span[^>]*class="c390"[^>]*>([^<]+)</span>', html_content)
    
    temp_low = temp_low_match.group(1) if temp_low_match else None
    temp_high = temp_high_match.group(1) if temp_high_match else None
    
    temp = f"{temp_low}～{temp_high}" if temp_low and temp_high else None
    
    return {
        '城市': city,
        '天气': weather,
        '气温': temp
    }

def get_weather(city:str)->str:
    """
    params: city - str 城市名称(中文)
    :return 城市、天气、气温 的json格式的字符串
    """
    
    p = Pinyin()
    pinyin_city = p.get_pinyin(city,'')

    # 设置请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Referer": "https://www.google.com/",
    }

    response = requests.get(f'https://i.tianqi.com/?c=code&a=getcode&id=6&py={pinyin_city}',headers=headers)

    return parse_weather_simple(response.text)

if __name__=='__main__':
    res = get_weather("北京")
    print(res)
    print(res['城市'])
    print(res['天气'])
    print(res['气温'])