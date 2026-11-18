#!/usr/bin/env python3
"""Safely append validated official Daily539 draws to existing draws.json."""
import datetime as dt
import json
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / 'draws.json'
API = 'https://api.taiwanlottery.com/TLCAPIWeB/Lottery/Daily539Result'
TZ = dt.timezone(dt.timedelta(hours=8))


def validate(row):
    if not isinstance(row, dict):
        return False
    try:
        date = dt.date.fromisoformat(row['date'])
        nums = row['nums']
        issue = row['issue']
    except (KeyError, TypeError, ValueError):
        return False
    return (dt.date(2007, 1, 1) <= date <= dt.datetime.now(TZ).date()
            and isinstance(nums, list) and len(nums) == 5
            and all(type(n) is int and 1 <= n <= 39 for n in nums)
            and len(set(nums)) == 5
            and isinstance(issue, str) and issue.isdigit() and len(issue) in (8, 9))


def month_shift(y, m, offset):
    n = y * 12 + (m - 1) + offset
    return f'{n // 12:04d}-{n % 12 + 1:02d}'


def fetch_month(month):
    url = API + '?' + urllib.parse.urlencode({'month': month, 'pageSize': 80})
    req = urllib.request.Request(url, headers={'User-Agent': 'Zhaixingguai539-GitHubUpdater/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.load(response)
    rows = payload.get('content', {}).get('daily539Res')
    if not isinstance(rows, list):
        raise ValueError(f'官方回傳格式不符合預期：{month}')
    return rows


def parse(item):
    if not isinstance(item, dict):
        return None
    date = str(item.get('lotteryDate', ''))[:10]
    issue = str(item.get('period', ''))
    raw = item.get('drawNumberAppear')
    if not isinstance(raw, list):
        return None
    try:
        nums = sorted(int(n) for n in raw)
    except (TypeError, ValueError):
        return None
    row = {'date': date, 'issue': issue, 'nums': nums}
    return row if validate(row) else None


def main():
    if not PATH.exists():
        raise RuntimeError('找不到 draws.json；請確認已上傳至儲存庫根目錄')
    existing = json.loads(PATH.read_text(encoding='utf-8-sig'))
    if not isinstance(existing, list) or len(existing) < 6000 or not all(validate(r) for r in existing):
        raise RuntimeError('原有歷史資料異常，停止更新以避免破壞資料')
    by_date = {}
    by_issue = {}
    for r in existing:
        if r['date'] in by_date or r['issue'] in by_issue:
            raise RuntimeError('原有資料出現重複日期或期別，停止更新')
        by_date[r['date']] = r
        by_issue[r['issue']] = r
    now = dt.datetime.now(TZ)
    months = [month_shift(now.year, now.month, -1), month_shift(now.year, now.month, 0)]
    incoming = []
    for month in months:
        incoming.extend(fetch_month(month))
    if not incoming:
        raise RuntimeError('官方未回傳任何開獎資料，不更新')
    parsed = [parse(item) for item in incoming]
    if not any(parsed):
        raise RuntimeError('官方資料無法安全解析日期與五顆號碼，不更新')
    if any(p is None for p in parsed):
        raise RuntimeError('官方資料含無效項目，不更新；請檢查官方格式')
    additions = []
    for r in sorted(parsed, key=lambda x: x['date']):
        old_date = by_date.get(r['date'])
        old_issue = by_issue.get(r['issue'])
        if old_date or old_issue:
            if (old_date is None or old_issue is None
                or old_date['date'] != old_issue['date']
                or old_date['nums'] != r['nums']):
                raise RuntimeError(f'資料衝突 {r["date"]} {r["issue"]}，不覆蓋舊資料')
            continue
        if r['date'] <= existing[-1]['date']:
            raise RuntimeError(f'發現缺漏的舊日期 {r["date"]}，請人工檢查')
        by_date[r['date']] = r
        by_issue[r['issue']] = r
        additions.append(r)
    if not additions:
        print(f'無新資料；最新 {existing[-1]["date"]} {existing[-1]["nums"]}')
        return
    combined = existing + additions
    if len({r['date'] for r in combined}) != len(combined):
        raise RuntimeError('日期重複，拒絕寫入')
    temp = PATH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(combined, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(PATH)
    print(f'新增 {len(additions)} 期；最新 {combined[-1]["date"]} {combined[-1]["nums"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'更新失敗：{exc}', file=sys.stderr)
        sys.exit(1)
