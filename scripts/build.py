#!/usr/bin/env python3
"""把網站檔案與 Google 試算表 CSV 組成 _site/，交給 GitHub Pages 發布。

試算表設定為「知道連結的人可檢視」，因此不需要任何金鑰。
CSV 只存在發布出去的網站裡，不會存進 Git 紀錄。
"""
import datetime as dt
import json
import pathlib
import shutil
import sys
import time
import urllib.request

SHEETS = {
    "cal": "1HQ02MEG6PlqPCZr_zp5nSfnB2LEr6rCIDhChI2TLffs",    # 03 年度行事曆
    "todo": "1ZWkJc1ilot2s8GneKnsD4npq2LgBQpR5Mf4smaPBDuw",   # 02 待辦追蹤表
    "mtg": "1ZS5IsVC1dL9HUyPrXR5ypuuavoEdF8-WamwKGEu0PRg",    # 01 會議記錄總表
    "doc": "1iRKSySM7T0LRll96DtT8fgPF_MsVyUksySv5w9Ds_jE",    # 04 申辦文書進度表
    "ev": "1dsCVh2H2n4ioPwgqdaetMzvSLoGOWZOtFoWMFtQmGWc",     # 05 大型活動期程表
    "lunar": "1QfNRelkiN4te8oU9seso6oAIytUG6lbyoH-XBVGhkVY",  # 06 農曆祭典推估
}
STATIC = ["index.html", "robots.txt", "workflow.json", "announcements.json", "github.json"]
OUT = pathlib.Path("_site")


def fetch(sheet_id, tries=3):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    for n in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                body = r.read()
            if body.lstrip().startswith(b"<"):
                raise RuntimeError("拿到的是網頁不是 CSV，請確認試算表仍是「知道連結的人可檢視」")
            return body
        except Exception as e:
            if n == tries - 1:
                raise
            print(f"重試 {sheet_id}：{e}")
            time.sleep(5)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    for f in STATIC:
        shutil.copy(f, OUT / f)
    failed = []
    for key, sid in SHEETS.items():
        try:
            (OUT / "data" / f"{key}.csv").write_bytes(fetch(sid))
            print("已匯入", key)
        except Exception as e:
            failed.append(key)
            print(f"::warning::{key} 匯入失敗：{e}")
    at = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="minutes")
    (OUT / "data" / "meta.json").write_text(json.dumps({"at": at, "failed": failed}, ensure_ascii=False))
    if len(failed) == len(SHEETS):
        sys.exit("所有試算表都匯入失敗，這次不發布")


if __name__ == "__main__":
    main()
