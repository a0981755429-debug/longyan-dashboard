#!/usr/bin/env python3
"""把網站檔案與 Google 試算表 CSV 組成 _site/，交給 GitHub Pages 發布。

每次發布會做四件事：
1. 讀取試算表（設定為「知道連結的人可檢視」，不需要金鑰）
2. 遮蔽敏感資訊：手機、市話、身分證字號、Email、地址、生日換成「＊」；欄名含電話／地址／身分證等的整欄移除
3. 檢查資料：必要欄位、筆數、日期格式、編號格式
4. 某份試算表讀取或檢查失敗時，沿用網站上一版的資料，並在頁面上標示

CSV 只存在發布出去的網站裡，不會存進 Git 紀錄。
"""
import csv
import datetime as dt
import io
import json
import os
import pathlib
import re
import shutil
import sys
import time
import urllib.request

import ics

TZ = dt.timezone(dt.timedelta(hours=8))
SITE_URL = os.environ.get("SITE_URL", "https://a0981755429-debug.github.io/longyan-dashboard/")

# key: (試算表 ID, 中文名稱, 必要欄位, 日期欄位)
SHEETS = {
    "todo": ("1ZWkJc1ilot2s8GneKnsD4npq2LgBQpR5Mf4smaPBDuw", "02 待辦追蹤表",
             ["編號", "活動代碼", "待辦事項", "負責", "期限", "狀態"], ["期限"]),
    "mtg": ("1ZS5IsVC1dL9HUyPrXR5ypuuavoEdF8-WamwKGEu0PRg", "01 會議記錄總表",
            ["會議名稱", "會議類型", "正式紀錄"], ["西元日期"]),
    "cal": ("1HQ02MEG6PlqPCZr_zp5nSfnB2LEr6rCIDhChI2TLffs", "03 年度行事曆",
            ["國曆日期", "活動", "類別", "日期狀態"], ["國曆日期", "建議開始籌備"]),
    "doc": ("1iRKSySM7T0LRll96DtT8fgPF_MsVyUksySv5w9Ds_jE", "04 申辦文書進度表",
            ["編號", "案件", "編別/項目", "內容大綱", "狀態"], ["到期日"]),
    "ev": ("1dsCVh2H2n4ioPwgqdaetMzvSLoGOWZOtFoWMFtQmGWc", "05 大型活動期程表",
           ["活動代碼", "大型活動", "活動日", "工作內容", "預估日期", "狀態"], ["活動日", "預估日期"]),
    "lunar": ("1QfNRelkiN4te8oU9seso6oAIytUG6lbyoH-XBVGhkVY", "06 農曆祭典推估",
              ["國曆日期", "活動", "項目", "類別", "可信度"], ["國曆日期"]),
    "rec": ("1osJl3bXDSt2G8u6_dsulcPm-Qb8yAYUTZsUJgzHuvgI", "09 公文與決議追蹤表",
            ["編號", "類型", "日期", "主旨／決議內容", "負責", "狀態"], ["日期", "期限"]),
}
STATIC = ["index.html", "robots.txt", "workflow.json", "announcements.json", "github.json"]
OUT = pathlib.Path("_site")

# ---- 敏感資訊遮蔽 ----
SENSITIVE = [
    ("手機", re.compile(r"(?<!\d)09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")),
    ("市話", re.compile(r"(?<!\d)\(?0[2-8]\)?[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")),
    ("身分證字號", re.compile(r"(?<![A-Za-z0-9])[A-Z][12489]\d{8}(?!\d)")),
    ("Email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    # 台灣地址：要有「路／街／道」加門牌「號」才算，避免把「中和區」這類地名誤遮
    ("地址", re.compile(r"(?:[\u4e00-\u9fff]{2}[縣市])?[\u4e00-\u9fff]{1,4}[區鄉鎮市]?[\u4e00-\u9fff0-9]{1,10}[路街道]"
                       r"(?:[一二三四五六七八九十\d]+段)?(?:\d+巷)?(?:\d+弄)?\d+(?:之\d+)?號(?:\d+樓)?")),
    ("出生日期", re.compile(r"(?:生日|出生)[：:\s]*\d{2,4}[./-]\d{1,2}[./-]\d{1,2}")),
]
# 欄位名稱符合這些字樣的整欄移除（就算內容格式辨識不出來也不會外流）；「承辦紀錄」是內部平台的工作筆記，也不公開
SENSITIVE_COLS = re.compile(r"承辦紀錄|電話|手機|市話|地址|住址|身分證|身份證|生日|出生|Email|E-mail|信箱|LINE\s*ID", re.I)

# ---- 編號規則（詳見 longyan-platform/docs/規範/編號規則.md）----
GANZHI = "[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
ACT_CODE = re.compile(rf"^({GANZHI}|行政|建設|會務)-\S+$")
ID_RULES = {"todo": ("編號", re.compile(r"^T\d{3}$")), "doc": ("編號", re.compile(r"^[A-Z]\d{2,3}$")),
            "rec": ("編號", re.compile(r"^[ROI]\d{3}$"))}
# 標準狀態（詳見 longyan-platform/docs/規範/狀態與權責.md）
STATUS_OK = {"todo": {"未開始", "進行中", "等待他人", "待確認", "已完成", "取消", "備忘"},
             "rec": {"未開始", "進行中", "等待他人", "待確認", "已完成", "取消", "備忘"}}
CODE_COLS = {"todo": "活動代碼", "ev": "活動代碼"}

DATE_OK = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
DATE_ROC = re.compile(r"^0?(\d{2,3})[./-](\d{1,2})[./-](\d{1,2})")


def fetch(url, tries=3):
    for n in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception as e:
            if n == tries - 1:
                raise
            print(f"重試 {url}：{e}")
            time.sleep(5)


def drop_sensitive_cols(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return text, []
    keep = [i for i, h in enumerate(rows[0]) if not SENSITIVE_COLS.search(h or "")]
    dropped = [h for i, h in enumerate(rows[0]) if i not in keep]
    if not dropped:
        return text, []
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([[r[i] if i < len(r) else "" for i in keep] for r in rows])
    return out.getvalue(), dropped


def mask(text):
    counts = {}
    for name, rx in SENSITIVE:
        text, n = rx.subn(lambda m: "＊" * len(m.group(0)), text)
        if n:
            counts[name] = n
    return text, counts


def check(key, text):
    _, name, required, date_cols = SHEETS[key]
    rows = list(csv.DictReader(io.StringIO(text)))
    head = [h.strip() for h in (rows[0].keys() if rows else csv.reader(io.StringIO(text)).__next__())]
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows]
    rows = [r for r in rows if any(r.values())]
    missing = [c for c in required if c not in head]
    bad_dates, roc_dates = [], 0
    for c in date_cols:
        for i, r in enumerate(rows, start=2):
            v = r.get(c, "")
            if not v or v in ("—", "-", "待定", "未定"):
                continue
            m = DATE_OK.match(v)
            if m and not re.match(r"^0\d{3}[-/]", v):
                try:
                    dt.date(int(m[1]), int(m[2]), int(m[3]))
                except ValueError:
                    bad_dates.append(f"第{i}列 {c}「{v[:12]}」日期不存在")
                continue
            if DATE_ROC.match(v) or re.match(r"^0\d{3}[-/]", v):
                roc_dates += 1
                bad_dates.append(f"第{i}列 {c}「{v[:12]}」是民國格式，請改成西元")
                continue
            bad_dates.append(f"第{i}列 {c}「{v[:12]}」")
    bad_ids = []
    if key in ID_RULES:
        col, rx = ID_RULES[key]
        bad_ids += [f"第{i}列 {col}「{r.get(col, '')[:10]}」" for i, r in enumerate(rows, start=2) if r.get(col) and not rx.match(r[col])]
        seen = {}
        for i, r in enumerate(rows, start=2):
            v = r.get(col)
            if v:
                if v in seen:
                    bad_ids.append(f"第{i}列 {col}「{v}」與第{seen[v]}列重複")
                seen.setdefault(v, i)
    if key in CODE_COLS:
        col = CODE_COLS[key]
        bad_ids += [f"第{i}列 {col}「{r.get(col, '')[:12]}」" for i, r in enumerate(rows, start=2) if r.get(col) and not ACT_CODE.match(r[col])]
    if key in STATUS_OK:
        bad_ids += [f"第{i}列 狀態「{r.get('狀態', '')[:8]}」不是標準狀態" for i, r in enumerate(rows, start=2)
                    if r.get("狀態") and r["狀態"] not in STATUS_OK[key]]
    return {"rows": len(rows), "missingCols": missing, "badDates": bad_dates[:20], "badDateCount": len(bad_dates),
            "rocDates": roc_dates, "badIds": bad_ids[:20], "badIdCount": len(bad_ids)}


def previous_meta():
    try:
        return json.loads(fetch(SITE_URL + "data/meta.json", tries=1))
    except Exception:
        return {}


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    for f in STATIC:
        shutil.copy(f, OUT / f)
    now = dt.datetime.now(TZ).isoformat(timespec="minutes")
    prev = previous_meta().get("sheets", {})
    sheets = {}
    for key, (sid, name, _, _) in SHEETS.items():
        info = {"name": name, "id": sid}
        try:
            body = fetch(f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv")
            if body.lstrip().startswith(b"<"):
                raise RuntimeError("拿到的是網頁不是 CSV，試算表可能已改成不公開或被刪除")
            text = body.decode("utf-8-sig")
            text, dropped = drop_sensitive_cols(text)
            text, masked = mask(text)
            info.update(check(key, text))
            if info["missingCols"]:
                raise RuntimeError("缺少必要欄位：" + "、".join(info["missingCols"]))
            if info["rows"] == 0:
                raise RuntimeError("試算表沒有任何資料列")
            (OUT / "data" / f"{key}.csv").write_text(text, encoding="utf-8")
            info.update(status="ok", masked=masked, droppedCols=dropped, sourceAt=now)
            print(f"已匯入 {name}：{info['rows']} 筆" + (f"，遮蔽 {masked}" if masked else "") + (f"，移除欄位 {dropped}" if dropped else ""))
        except Exception as e:
            info["error"] = str(e)[:200]
            try:
                old = fetch(SITE_URL + f"data/{key}.csv", tries=2).decode("utf-8-sig")
                # 上一版發布前已遮蔽過；這裡用最新規則再處理一次，規則變嚴時舊資料也跟著變嚴
                old, _ = drop_sensitive_cols(old)
                old, _ = mask(old)
                (OUT / "data" / f"{key}.csv").write_text(old, encoding="utf-8")
                info.update(status="fallback", sourceAt=prev.get(key, {}).get("sourceAt"))
                print(f"::warning::{name} 匯入失敗，沿用上一版：{e}")
            except Exception:
                info["status"] = "failed"
                print(f"::error::{name} 匯入失敗，也沒有上一版可用：{e}")
        for k in ("badDateCount", "badIdCount"):
            if info.get(k):
                print(f"::notice::{name} {k}={info[k]}：" + "；".join((info.get('badDates') if k == 'badDateCount' else info.get('badIds'))[:5]))
        sheets[key] = info
    (OUT / "data" / "meta.json").write_text(json.dumps({"at": now, "sheets": sheets}, ensure_ascii=False, indent=1), encoding="utf-8")
    # iPhone／Google 行事曆訂閱檔（用剛寫好的已遮蔽 CSV 產生）
    try:
        n = ics.build(OUT / "data", OUT / "calendar.ics", SITE_URL, OUT / "announcements.json")
        print(f"已產生 calendar.ics：{n} 筆行程")
    except Exception as e:
        print(f"::warning::calendar.ics 產生失敗：{e}")
    if all(s["status"] == "failed" for s in sheets.values()):
        sys.exit("所有試算表都無法取得，這次不發布")


if __name__ == "__main__":
    main()
