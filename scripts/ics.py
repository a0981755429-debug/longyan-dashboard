#!/usr/bin/env python3
"""把 03 年度行事曆與 05 大型活動期程表組成 iPhone／Google 行事曆可訂閱的 calendar.ics。

規則：
- 05 大型活動期程表的每個工作階段都是一個全天行程（活動日當天的階段標示為主行程）。
- 03 年度行事曆的列，如果同一個活動代碼已出現在 05，就以 05 為準（不重複列）；其餘照 03 列入。
- 工作內容寫「（三日）」「（共3日…）」這類字樣時，行程跨多天。
- 狀態「取消」不列；「已完成」保留但不提醒；其餘在前一天上午 9:00 提醒。
- UID 由「來源＋活動代碼＋項目名稱」產生，日期改了 iPhone 會更新同一筆，不會多出一筆。
- 只用已發布到網站、已遮蔽過的 CSV，不額外公開任何欄位；備註欄不放進行事曆。
"""
import csv
import datetime as dt
import hashlib
import io
import pathlib
import re

TZ = dt.timezone(dt.timedelta(hours=8))
CN_NUM = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
DAYS = re.compile(r"[（(](?:共)?([一二兩三四五六七\d])日")


def _rows(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    rows = csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig")))
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows]


def _date(v):
    m = DATE.match(v or "")
    if not m:
        return None
    try:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _days(text):
    m = DAYS.search(text or "")
    if not m:
        return 1
    n = m[1]
    return int(n) if n.isdigit() else CN_NUM.get(n, 1)


def _esc(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line):
    """RFC 5545：每行最多 75 bytes，續行以空白開頭（不切斷中文字）。"""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur)
            cur = b""
        cur += b
    out.append(cur)
    return "\r\n ".join(x.decode("utf-8") for x in out)


def collect(data_dir):
    data_dir = pathlib.Path(data_dir)
    ev, cal = _rows(data_dir / "ev.csv"), _rows(data_dir / "cal.csv")
    ev_codes = {r.get("活動代碼") for r in ev if r.get("活動代碼")}
    items = []
    for r in ev:
        d = _date(r.get("預估日期"))
        work = r.get("工作內容", "")
        if not d or not work or r.get("狀態") == "取消":
            continue
        code = r.get("活動代碼", "")
        short = code.split("-", 1)[-1] if "-" in code else (r.get("大型活動") or "")
        main = r.get("距活動日", "").replace("\\", "") == "0"
        title = work if main else f"{short}｜{work}"
        desc = [f"大型活動：{r.get('大型活動', '')}", f"負責：{r.get('負責', '')}", f"狀態：{r.get('狀態', '')}"]
        if r.get("依據"):
            desc.append(f"依據：{r['依據']}")
        # 主行程的天數也看活動名稱，例如「丁未年進香（二日）」
        days = max(_days(work), _days(r.get("大型活動", ""))) if main else _days(work)
        items.append(dict(uid=("ev", code, work), date=d, days=days, title=title,
                          cat="大型活動" if main else "籌備工作", desc=desc, done=r.get("狀態") == "已完成"))
    for r in cal:
        d = _date(r.get("國曆日期"))
        name = r.get("活動", "")
        code = r.get("活動代碼", "")
        if not d or not name or code in ev_codes:
            continue
        status = r.get("日期狀態", "")
        title = name if status in ("已決議", "") else f"{name}（{status}）"
        desc = [f"類別：{r.get('類別', '')}", f"主辦：{r.get('主辦', '')}", f"日期狀態：{status}"]
        if r.get("農曆"):
            desc.insert(0, f"農曆：{r['農曆']}")
        if r.get("依據與備註"):
            desc.append(f"依據：{r['依據與備註']}")
        items.append(dict(uid=("cal", code, name), date=d, days=_days(name), title=title,
                          cat=r.get("類別") or "行事曆", desc=desc, done=False))
    items.sort(key=lambda x: (x["date"], x["title"]))
    return items


def build(data_dir, out_path, site_url):
    items = collect(data_dir)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    today = dt.datetime.now(TZ).date()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Longyan Temple//Work Calendar//ZH-TW",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:龍延宮工作行事曆",
             "X-WR-CALDESC:" + _esc("03 年度行事曆＋05 大型活動期程表（同活動以 05 為準），每 30 分鐘自動更新"),
             "X-WR-TIMEZONE:Asia/Taipei", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for it in items:
        uid = hashlib.sha1("|".join(it["uid"]).encode("utf-8")).hexdigest()[:20]
        end = it["date"] + dt.timedelta(days=it["days"])
        ev = ["BEGIN:VEVENT", f"UID:{uid}@longyan-dashboard", f"DTSTAMP:{stamp}",
              f"DTSTART;VALUE=DATE:{it['date']:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}",
              "SUMMARY:" + _esc(("✓ " if it["done"] else "") + it["title"]),
              "DESCRIPTION:" + _esc("\n".join(it["desc"] + ["", "網站：" + site_url])),
              "CATEGORIES:" + _esc(it["cat"]), "TRANSP:TRANSPARENT", f"URL:{site_url}"]
        if not it["done"] and end > today:
            # 全天行程從 00:00 起算，往前 15 小時＝前一天 09:00
            ev += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _esc("明天：" + it["title"]),
                   "TRIGGER:-PT15H", "END:VALARM"]
        ev.append("END:VEVENT")
        lines += ev
    lines.append("END:VCALENDAR")
    pathlib.Path(out_path).write_text("\r\n".join(_fold(l) for l in lines) + "\r\n", encoding="utf-8", newline="")
    return len(items)


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1], sys.argv[2], "https://a0981755429-debug.github.io/longyan-dashboard/"), "筆")
