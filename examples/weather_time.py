import json
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


WEATHER_CODE_MAP_EN = {
    0: 'clear', 1: 'mostly clear', 2: 'partly cloudy', 3: 'cloudy',
    45: 'fog', 48: 'rime fog', 51: 'light drizzle', 53: 'drizzle', 55: 'dense drizzle',
    61: 'light rain', 63: 'rain', 65: 'heavy rain', 71: 'light snow', 73: 'snow', 75: 'heavy snow',
    80: 'rain showers', 81: 'showers', 82: 'heavy showers', 95: 'thunderstorm',
}
WEATHER_CODE_MAP_ZH = {
    0: '晴', 1: '基本晴', 2: '局部多云', 3: '多云',
    45: '有雾', 48: '雾凇', 51: '小毛雨', 53: '毛雨', 55: '强毛雨',
    61: '小雨', 63: '下雨', 65: '大雨', 71: '小雪', 73: '下雪', 75: '大雪',
    80: '阵雨', 81: '阵雨', 82: '强阵雨', 95: '雷暴',
}


def current_time_text(locale: str = 'en', timezone_name: Optional[str] = None) -> str:
    if timezone_name and ZoneInfo is not None:
        now = datetime.now(ZoneInfo(timezone_name))
    else:
        now = datetime.now().astimezone()
    zone_name = str(now.tzinfo)
    if locale == 'zh':
        return f"当前时间 {now.strftime('%H:%M')}，时区 {zone_name}"
    return f"Current time {now.strftime('%H:%M')} in {zone_name}"


def geocode_location(location: str):
    url = 'https://nominatim.openstreetmap.org/search?q=' + urllib.parse.quote(location) + '&format=jsonv2&limit=1'
    request = urllib.request.Request(url, headers={'User-Agent': 'frame-glasses/1.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    if not data:
        raise RuntimeError(f'Location not found: {location}')
    item = data[0]
    return float(item['lat']), float(item['lon']), item.get('display_name', location)


def fetch_weather(location: str, locale: str = 'en') -> str:
    lat, lon, label = geocode_location(location)
    url = (
        'https://api.open-meteo.com/v1/forecast?latitude=' + str(lat) +
        '&longitude=' + str(lon) +
        '&current=temperature_2m,apparent_temperature,weather_code&timezone=auto'
    )
    with urllib.request.urlopen(url, timeout=15) as response:
        data = json.load(response)
    current = data['current']
    code = int(current.get('weather_code', -1))
    temperature = current.get('temperature_2m')
    apparent = current.get('apparent_temperature')
    desc = (WEATHER_CODE_MAP_ZH if locale == 'zh' else WEATHER_CODE_MAP_EN).get(code, str(code))
    short_label = location
    if locale == 'zh':
        return f"{short_label} 当前 {desc}，{temperature} 度，体感 {apparent} 度"
    return f"{short_label} is {desc}, {temperature} degrees, feels like {apparent}"
