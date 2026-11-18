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
            and isinstance(issue, str) and (issue == '' or (issue.isdigit() and len(issue) in (8, 9))))


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
    return row if validate(row) and row['issue'] != '' else None


def main():
    if not PATH.exists():
        raise RuntimeError('找不到 draws.json；請確認檔案位於儲存庫根目錄')
    existing = json.loads(PATH.read_text(encoding='utf-8-sig'))
    if not isinstance(existing, list) or len(existing) < 6000 or not all(validate(r) for r in existing):
        raise RuntimeError('原有歷史資料格式或號碼異常，停止更新')
    dates = [r['date'] for r in existing]
    issues = [r['issue'] for r in existing if r['issue']]
    if dates != sorted(dates) or len(set(dates)) != len(dates) or len(set(issues)) != len(issues):
        raise RuntimeError('原有資料日期順序、重複日期或期別異常，停止更新')

    by_date = {r['date']: dict(r) for r in existing}
    by_issue = {r['issue']: r['date'] for r in existing if r['issue']}
    now = dt.datetime.now(TZ)
    months = [month_shift(now.year, now.month, -1), month_shift(now.year, now.month, 0)]
    incoming = []
    for month in months:
        incoming.extend(fetch_month(month))
    if not incoming:
        raise RuntimeError('官方未回傳任何開獎資料，不更新')
    parsed = [parse(item) for item in incoming]
    if not any(parsed) or any(p is None for p in parsed):
        raise RuntimeError('官方資料無法安全解析，停止更新')

    additions = []
    repairs = 0
    for r in sorted(parsed, key=lambda x: x['date']):
        date, issue = r['date'], r['issue']
        prior_date = by_issue.get(issue)
        if prior_date is not None and prior_date != date:
            raise RuntimeError(f'官方期別 {issue} 與原有日期衝突，停止更新')
        old = by_date.get(date)
        if old is not None:
            if old['nums'] != r['nums']:
                raise RuntimeError(f'官方號碼與既有資料衝突：{date}，停止更新')
            if old['issue'] and old['issue'] != issue:
                raise RuntimeError(f'官方期別與既有資料衝突：{date}，停止更新')
            if not old['issue']:
                old['issue'] = issue  # Only fill when date AND five numbers match official response
                repairs += 1
        else:
            if date <= existing[-1]['date']:
                raise RuntimeError(f'發現缺漏的歷史日期 {date}，停止更新並請人工核對')
            by_date[date] = r
            additions.append(r)
        by_issue[issue] = date

    combined = [by_date[r['date']] for r in existing] + additions
    if not all(validate(r) for r in combined):
        raise RuntimeError('更新後驗證失敗，拒絕寫入')
    if not additions and not repairs:
        print(f'無新資料；最新 {existing[-1]["date"]}')
        return
    temp = PATH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(combined, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(PATH)
    print(f'新增 {len(additions)} 期，核對官方資料補齊 {repairs} 筆期別；最新 {combined[-1]["date"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'更新失敗：{exc}', file=sys.stderr)
        sys.exit(1)
