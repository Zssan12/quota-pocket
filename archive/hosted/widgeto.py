"""Widgeto table adapter. Import format follows widgeto.app's public exporter.

The format has not yet been verified on an iPhone. Never put provider keys in it.
"""
import datetime as dt
import time

from icloud_sync import quota_projection


def widgeto_config(url, reader_token):
    return {
        'name': '额度口袋',
        'subtitle': '平台额度 · 以采集时间为准',
        'api': {'sourceType': 'api', 'url': url, 'method': 'GET',
                'headers': [{'name': 'Authorization', 'value': 'Bearer ' + reader_token}],
                'filePath': None, 'fileBookmark': None},
        'render': {'type': 'table', 'table': {
            'source': "${api['items']}",
            'headers': ['账户', '额度', '采集时间'],
            'fields': ["${item['account']}", "${item['quota']}", "${item['freshness']}"],
        }},
    }


def widgeto_data(snapshot, current_time=None):
    current_time = time.time() if current_time is None else current_time
    clean = quota_projection(snapshot)
    ttl = clean.get('staleAfterSeconds', 630)
    items = []
    for row in clean['providers']:
        captured = row.get('lastSuccessAt')
        age = None
        if captured:
            age = current_time - dt.datetime.fromisoformat(captured.replace('Z', '+00:00')).timestamp()
        stale = age is None or age < -60 or age > ttl or row.get('status') != 'ok'
        if age is None or age < -60:
            freshness = '尚无有效采集时间'
        elif age < 60:
            freshness = '刚刚采集'
        elif age < 3600:
            freshness = '%d 分钟前采集' % (age // 60)
        elif age < 86400:
            freshness = '%d 小时前采集' % (age // 3600)
        else:
            freshness = '%d 天前采集' % (age // 86400)
        if stale:
            freshness = '旧数据 · ' + freshness
        values = []
        for window in row['windows']:
            value = window.get('remainingPercent')
            amount = '未知' if value is None else '%g%%' % value
            values.append(window.get('label', '额度') + ' ' + amount)
        for balance in row['balances']:
            value = balance.get('value')
            amount = '未知' if value is None else '%g %s' % (value, balance.get('unit', ''))
            values.append(balance.get('label', '余额') + ' ' + amount)
        items.append({'account': row['name'], 'quota': ' / '.join(values) or '尚无额度数据',
                      'freshness': freshness, 'lastSuccessAt': captured, 'stale': stale})
    if not items:
        items.append({'account': '额度口袋', 'quota': '尚未选择或采集账户',
                      'freshness': '请在电脑端连接数据源', 'lastSuccessAt': None, 'stale': True})
    return {'items': items, 'lastCollectionAt': clean.get('lastCollectionAt')}
