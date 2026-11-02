"""Current weather and a short forecast from Open-Meteo public HTTPS APIs."""
from __future__ import annotations

import json
from urllib.parse import quote, urlencode

from .web_fetch import read_webpage

_read = read_webpage
_CODES = {0: '晴', 1: '大致晴朗', 2: '多云', 3: '阴', 45: '雾', 48: '雾凇',
          51: '小毛毛雨', 53: '毛毛雨', 55: '强毛毛雨', 61: '小雨', 63: '中雨', 65: '大雨',
          71: '小雪', 73: '中雪', 75: '大雪', 80: '阵雨', 81: '较强阵雨', 82: '强阵雨',
          95: '雷暴', 96: '雷暴伴小冰雹', 99: '雷暴伴冰雹'}


def _json(url: str) -> dict:
    page = _read(url, max_chars=8000)
    try:
        data = json.loads(page['text'])
    except (KeyError, TypeError, json.JSONDecodeError):
        raise RuntimeError('天气服务返回了无效数据。') from None
    if not isinstance(data, dict):
        raise RuntimeError('天气服务返回了无效数据。')
    return data


def get_weather(location: str, days: int = 3) -> dict:
    """查询地点当前天气和1～7天预报。"""
    if not isinstance(location, str) or not location.strip() or len(location) > 100:
        raise ValueError('地点须为1～100字符。')
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError('days必须在1～7之间。')
    geo = _json('https://geocoding-api.open-meteo.com/v1/search?' + urlencode(
        {'name': location.strip(), 'count': 1, 'language': 'zh', 'format': 'json'}))
    rows = geo.get('results') or []
    if not rows:
        raise ValueError('没有找到这个地点。')
    place = rows[0]
    params = {'latitude': place['latitude'], 'longitude': place['longitude'],
              'current': 'temperature_2m,apparent_temperature,weather_code,wind_speed_10m',
              'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
              'forecast_days': days, 'timezone': place.get('timezone', 'auto')}
    data = _json('https://api.open-meteo.com/v1/forecast?' + urlencode(params))
    current = data.get('current') or {}
    current['weather'] = _CODES.get(current.get('weather_code'), '未知')
    daily = data.get('daily') or {}
    forecast = []
    for i, date in enumerate(daily.get('time', [])):
        def value(key):
            values = daily.get(key) or []
            return values[i] if i < len(values) else None
        code = value('weather_code')
        forecast.append({'date': date, 'weather': _CODES.get(code, '未知'),
                         'temperature_max': value('temperature_2m_max'),
                         'temperature_min': value('temperature_2m_min'),
                         'precipitation_probability_max': value('precipitation_probability_max')})
    label = ', '.join(str(x) for x in (place.get('name'), place.get('admin1'), place.get('country')) if x)
    return {'location': label, 'coordinates': {'latitude': place['latitude'], 'longitude': place['longitude']},
            'current': current, 'forecast': forecast, 'provider': 'open-meteo', 'untrusted': True}
