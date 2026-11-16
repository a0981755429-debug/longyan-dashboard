#!/usr/bin/env python3
"""把網站月曆上的所有行程組成 iPhone／Google 行事曆可訂閱的 calendar.ics。

內容（與網站「行事月曆」相同的種類，再加上 05 的籌備階段）：
- 03 年度行事曆：同一個活動代碼已出現在 05 時以 05 為準，不重複列。
- 05 大型活動期程表：每個工作階段一筆；活動日當天的階段為主行程。
- 06 農曆祭典推估：神明聖誕、團拜、犒軍、例行工作等；有「時間」（如 22:00）就排在那個時間。
- 02 待辦追蹤表：未完成且有期限的待辦，排在期限當天。
- 04 申辦文書進度表：未完成且有到期日的項目。
- 09 公文與決議追蹤表：未完成且有期限的項目。
- 公告排程（announcements.json）：排在發布日期與時間，內容放公告草稿，方便手機上複製。

其他規則：
- 工作內容寫「（三日）」「（共3日…）」這類字樣時，行程跨多天。
- 狀態「取消」不列；「已完成」標 ✓ 不提醒；其餘在前一天上午 9:00 提醒（公告排程不另外提醒）。
- 同一天、同名稱的行程只留一筆（先出現的為準：05 → 03 → 06 → 其他）。
- UID 由「來源＋名稱」產生，日期改了 iPhone 會更新同一筆，不會多出一筆。
- 只用已發布到網站、已遮蔽過的資料；試算表的「備註」欄不放進行事曆。
"""
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import re

TZ = dt.timezone(dt.timedelta(hours=8))
CN_NUM = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
DAYS = re.compile(r"[（(](?:共)?([一二兩三四五六七\d])日")
TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)(?!\d)")
CLOSED = {"已完成", "取消", "備忘"}


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


def _time(v):
    m = TIME.search(v or "")
    return dt.time(int(m[1]), int(m[2])) if m else None


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


def _desc(*pairs):
    return [f"{k}：{v}" for k, v in pairs if v]


def _item(src, key, d, title, cat, desc, done=False, days=1, at=None, alarm=True):
    return dict(uid=(src, key), date=d, days=days, at=at, title=title, cat=cat, desc=desc, done=done, alarm=alarm)


def from_ev(rows):
    out = []
    for r in rows:
        d = _date(r.get("預估日期"))
        work = r.get("工作內容", "")
        if not d or not work or r.get("狀態") == "取消":
            continue
        code = r.get("活動代碼", "")
        short = code.split("-", 1)[-1] if "-" in code else (r.get("大型活動") or "")
        main = r.get("距活動日", "").replace("\\", "") == "0"
        # 主行程的天數也看活動名稱，例如「丁未年進香（二日）」
        days = max(_days(work), _days(r.get("大型活動", ""))) if main else _days(work)
        out.append(_item("ev", code + "|" + work, d, work if main else f"{short}｜{work}",
                         "大型活動" if main else "籌備工作",
                         _desc(("大型活動", r.get("大型活動")), ("負責", r.get("負責")), ("狀態", r.get("狀態")),
                               ("依據", r.get("依據"))),
                         done=r.get("狀態") == "已完成", days=days))
    return out


def from_cal(rows, skip_codes):
    out = []
    for r in rows:
        d = _date(r.get("國曆日期"))
        name, code = r.get("活動", ""), r.get("活動代碼", "")
        if not d or not name or code in skip_codes:
            continue
        status = r.get("日期狀態", "")
        title = name if status in ("已決議", "") else f"{name}（{status}）"
        out.append(_item("cal", code + "|" + name, d, title, r.get("類別") or "行事曆",
                         _desc(("農曆", r.get("農曆")), ("類別", r.get("類別")), ("主辦", r.get("主辦")),
                               ("日期狀態", status), ("依據", r.get("依據與備註"))), days=_days(name)))
    return out


def from_lunar(rows):
    out = []
    for r in rows:
        d = _date(r.get("國曆日期"))
        name = r.get("項目") or r.get("活動", "")
        if not d or not name:
            continue
        out.append(_item("lunar", f"{r.get('活動', '')}|{name}|{d.year}", d, name, r.get("類別") or "農曆祭典",
                         _desc(("活動", r.get("活動")), ("農曆", r.get("農曆")), ("時間", r.get("時間")),
                               ("說明", r.get("說明／工作內容")), ("類別", r.get("類別")), ("可信度", r.get("可信度"))),
                         at=_time(r.get("時間")), days=_days(name)))
    return out


def from_open(rows, src, date_col, title_fn, label, desc_fn):
    out = []
    for r in rows:
        d = _date(r.get(date_col))
        if not d or r.get("狀態") in CLOSED:
            continue
        title = title_fn(r)
        if not title:
            continue
        out.append(_item(src, (r.get("編號") or "") + "|" + title, d, f"{label}｜{title}", label, desc_fn(r)))
    return out


def from_ann(items):
    out = []
    for a in items or []:
        d = _date(a.get("發布日期"))
        title = a.get("標題") or a.get("活動") or ""
        if not d or not title:
            continue
        out.append(_item("ann", f"{a.get('發布日期')}|{a.get('發布時間')}|{title}", d, "公告｜" + title.strip("【】"),
                         "公告排程",
                         _desc(("公告類型", a.get("公告類型")), ("活動", a.get("活動")),
                               ("對應工作日期", a.get("對應工作日期")), ("對應農曆", a.get("對應農曆")),
                               ("可信度", a.get("可信度"))) + ["", a.get("公告內容草稿", "")],
                         at=_time(a.get("發布時間")), alarm=False))
    return out


def collect(data_dir, ann_path=None):
    data_dir = pathlib.Path(data_dir)
    r = {k: _rows(data_dir / f"{k}.csv") for k in ("ev", "cal", "lunar", "todo", "doc", "rec")}
    ann = []
    if ann_path and pathlib.Path(ann_path).exists():
        try:
            ann = json.loads(pathlib.Path(ann_path).read_text(encoding="utf-8"))
        except ValueError:
            ann = []
    ev_codes = {x.get("活動代碼") for x in r["ev"] if x.get("活動代碼")}
    items = (from_ev(r["ev"]) + from_cal(r["cal"], ev_codes) + from_lunar(r["lunar"])
             + from_open(r["todo"], "todo", "期限", lambda x: x.get("待辦事項"), "待辦",
                         lambda x: _desc(("編號", x.get("編號")), ("活動代碼", x.get("活動代碼")), ("負責", x.get("負責") or "未指派"),
                                         ("優先", x.get("優先")), ("狀態", x.get("狀態"))))
             + from_open(r["doc"], "doc", "到期日", lambda x: x.get("內容大綱") or x.get("編別/項目"), "申辦",
                         lambda x: _desc(("編號", x.get("編號")), ("案件", x.get("案件")), ("項目", x.get("編別/項目")),
                                         ("負責", x.get("負責")), ("狀態", x.get("狀態"))))
             + from_open(r["rec"], "rec", "期限", lambda x: x.get("主旨／決議內容") or x.get("來源"), "文書期限",
                         lambda x: _desc(("編號", x.get("編號")), ("類型", x.get("類型")), ("來源", x.get("來源")),
                                         ("負責", x.get("負責")), ("狀態", x.get("狀態"))))
             + from_ann(ann))
    seen, out = set(), []
    for it in items:
        k = (it["date"], it["title"].lstrip("✓ "))
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    out.sort(key=lambda x: (x["date"], x["at"] or dt.time(0), x["title"]))
    return out


def build(data_dir, out_path, site_url, ann_path=None):
    items = collect(data_dir, ann_path)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    now = dt.datetime.now(TZ)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Longyan Temple//Work Calendar//ZH-TW",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:龍延宮工作行事曆",
             "X-WR-CALDESC:" + _esc("網站行事月曆的全部行程（行事曆、大型活動、農曆祭典、待辦、申辦、公文、公告排程），每 30 分鐘自動更新"),
             "X-WR-TIMEZONE:Asia/Taipei", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for it in items:
        uid = hashlib.sha1("|".join(it["uid"]).encode("utf-8")).hexdigest()[:20]
        ev = ["BEGIN:VEVENT", f"UID:{uid}@longyan-dashboard", f"DTSTAMP:{stamp}"]
        if it["at"]:
            start = dt.datetime.combine(it["date"], it["at"], TZ)
            end = start + dt.timedelta(hours=1)
            utc = lambda x: x.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            ev += [f"DTSTART:{utc(start)}", f"DTEND:{utc(end)}"]
        else:
            start = dt.datetime.combine(it["date"], dt.time(0), TZ)
            end = start + dt.timedelta(days=it["days"])
            ev += [f"DTSTART;VALUE=DATE:{it['date']:%Y%m%d}", f"DTEND;VALUE=DATE:{end.date():%Y%m%d}"]
        ev += ["SUMMARY:" + _esc(("✓ " if it["done"] else "") + it["title"]),
               "DESCRIPTION:" + _esc("\n".join(it["desc"] + ["", "網站：" + site_url])),
               "CATEGORIES:" + _esc(it["cat"]), "TRANSP:TRANSPARENT", f"URL:{site_url}"]
        if it["alarm"] and not it["done"] and end > now:
            # 前一天 09:00 提醒
            before = start - dt.datetime.combine(it["date"] - dt.timedelta(days=1), dt.time(9), TZ)
            mins = int(before.total_seconds() // 60)
            ev += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _esc("明天：" + it["title"]),
                   f"TRIGGER:-PT{mins}M", "END:VALARM"]
        ev.append("END:VEVENT")
        lines += ev
    lines.append("END:VCALENDAR")
    pathlib.Path(out_path).write_text("\r\n".join(_fold(l) for l in lines) + "\r\n", encoding="utf-8", newline="")
    return len(items)


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1], sys.argv[2], "https://a0981755429-debug.github.io/longyan-dashboard/",
                sys.argv[3] if len(sys.argv) > 3 else None), "筆")
