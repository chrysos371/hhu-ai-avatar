import json

import avatar.tools.weather as weather


def test_weather_geocodes_and_normalizes_forecast(monkeypatch):
    def read(url, max_chars=8000):
        if 'geocoding-api' in url:
            data = {'results': [{'name': '南京', 'country': '中国', 'latitude': 32.06, 'longitude': 118.78, 'timezone': 'Asia/Shanghai'}]}
        else:
            data = {'current': {'time': '2026-11-02T12:00', 'temperature_2m': 19.2, 'apparent_temperature': 18.4,
                                'weather_code': 2, 'wind_speed_10m': 8.1},
                    'daily': {'time': ['2026-11-02', '2026-11-03'], 'temperature_2m_max': [21, 22],
                              'temperature_2m_min': [13, 14], 'precipitation_probability_max': [10, 30],
                              'weather_code': [2, 3]}}
        return {'text': json.dumps(data), 'url': url}
    monkeypatch.setattr(weather, '_read', read)
    result = weather.get_weather('南京', days=2)
    assert result['location'] == '南京, 中国'
    assert result['current']['weather'] == '多云'
    assert result['forecast'][1]['precipitation_probability_max'] == 30


def test_weather_rejects_empty_location():
    try:
        weather.get_weather('')
    except ValueError as exc:
        assert '地点' in str(exc)
    else:
        raise AssertionError('empty location accepted')
