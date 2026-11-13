# 龍延宮工作平台・線上儀表板

網站：https://a0981755429-debug.github.io/longyan-dashboard/

- 每 30 分鐘自動從 Google 試算表（01–06）讀取資料並重新發布；改試算表就好，不用改這裡。
- 本倉庫只放網站程式，**不放任何資料**。試算表 CSV 只在發布時抓取，不會存進 Git 紀錄。
- 網站設定不被搜尋引擎收錄（robots.txt、noindex），但知道網址的人都看得到，請勿在試算表放個資。
- 規劃、待辦卡、小龍程式在私人倉庫 `longyan-platform`。

| 檔案 | 用途 |
|---|---|
| `index.html` | 網站本體 |
| `scripts/build.py` | 讀取試算表、組成網站 |
| `.github/workflows/deploy.yml` | 自動發布排程 |
| `workflow.json` | 活動流程（整理自 LINE 群組紀錄） |
| `announcements.json` | 回宮工作公告排程 |
| `github.json` | GitHub 規劃區塊資料 |
