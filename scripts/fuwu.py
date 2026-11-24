#!/usr/bin/env python3
"""產生公開服務頁 _site/fuwu/（讓附近的信眾在 Google 搜得到本宮）。

資料只來自 fuwu/services.json。看板本身仍是 noindex；只有這裡產生的頁面允許 Google 收錄。
價格、日期沒填就顯示「公告後更新」，不放舊資料。
"""
import datetime as dt
import html
import json
import pathlib

WEEK = "一二三四五六日"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def cta(t):
    """頁尾行動按鈕：有 LINE 連結就放「加 LINE」，否則請信眾來電。"""
    out = []
    if t.get("line_url"):
        out.append(f'<a class="btn line" href="{esc(t["line_url"])}" rel="noopener">加 LINE 登記・洽詢</a>')
    out.append(f'<a class="btn" href="tel:{esc(t["phone"].replace("(", "").replace(")", "").replace(" ", "").replace("-", ""))}">來電 {esc(t["phone"])}</a>')
    if t.get("map_url"):
        out.append(f'<a class="btn ghost" href="{esc(t["map_url"])}" rel="noopener">📍 Google 地圖導航</a>')
    if t.get("fb_url"):
        out.append(f'<a class="btn ghost" href="{esc(t["fb_url"])}" rel="noopener">臉書粉專</a>')
    return '<div class="cta">' + "".join(out) + "</div>"


CSS = """
:root{--red:#9b1c1c;--gold:#c8962e;--ink:#2a1a12;--bg:#fbf6ec;--card:#fff;--muted:#6b5a4c}
@media (prefers-color-scheme:dark){:root{--ink:#f3e9d8;--bg:#1d1410;--card:#2a1e17;--muted:#c4b29c;--red:#e06a5a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.75 "Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif}
header{background:#9b1c1c;color:#fff;padding:20px 16px;border-bottom:4px solid var(--gold)}
header a{color:#fff;text-decoration:none}header .t{font-size:22px;font-weight:700;letter-spacing:.05em}header .s{opacity:.9;font-size:14px}
main{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:26px;margin:8px 0 4px;color:var(--red)}h2{font-size:19px;margin:24px 0 6px;border-left:4px solid var(--gold);padding-left:8px}
.lead{font-size:18px;color:var(--muted)}
.card{background:var(--card);border-radius:10px;padding:14px 16px;margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card a{color:inherit;text-decoration:none;display:block}.card b{color:var(--red)}
ul{padding-left:1.2em}.muted{color:var(--muted);font-size:15px}
.cta{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.btn{flex:1 1 200px;text-align:center;padding:12px 14px;border-radius:999px;background:#9b1c1c;color:#fff;text-decoration:none;font-weight:700}
.btn.line{background:#06c755}.btn.ghost{background:transparent;color:var(--ink);border:1.5px solid var(--gold)}
table{width:100%;border-collapse:collapse;font-size:16px}td,th{padding:8px 6px;border-bottom:1px solid rgba(128,128,128,.25);text-align:left;vertical-align:top}
footer{max-width:760px;margin:0 auto;padding:16px 16px 40px;color:var(--muted);font-size:14px}
"""


def page(t, title, desc, body, url, ld=None):
    ldj = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld else ""
    return f"""<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<style>{CSS}</style>{ldj}</head><body>
<header><a href="./"><div class="t">{esc(t['name'])}</div><div class="s">主祀{esc(t['deity'])}・{esc(t['address'])}</div></a></header>
<main>{body}{cta(t)}</main>
<footer>{esc(t['name'])}｜{esc(t['address'])}｜電話 {esc(t['phone'])}<br>各項日期與費用以本宮正式公告為準。</footer>
</body></html>"""


def temple_ld(t, base):
    ld = {"@context": "https://schema.org", "@type": "PlaceOfWorship", "name": t["name"], "url": base,
          "telephone": t["phone"],
          "address": {"@type": "PostalAddress", "streetAddress": "興南路三段133號", "addressLocality": "中和區",
                      "addressRegion": "新北市", "postalCode": "235", "addressCountry": "TW"}}
    same = [u for u in (t.get("fb_url"), t.get("line_url"), t.get("map_url")) if u]
    if same:
        ld["sameAs"] = same
    return ld


def build(src: pathlib.Path, out: pathlib.Path, site_url: str):
    d = json.loads(src.read_text(encoding="utf-8"))
    t = d["temple"]
    base = site_url.rstrip("/") + "/fuwu/"
    out.mkdir(parents=True, exist_ok=True)
    urls = [base]

    # 各服務頁
    for s in d["services"]:
        url = base + s["slug"] + ".html"
        urls.append(url)
        price = esc(s["price"]) if s.get("price") else f"{esc(d['year_label'])}費用公告後更新，請來電或私訊洽詢。"
        body = (f'<h1>{esc(s["name"])}</h1><p class="lead">{esc(s["summary"])}</p>'
                f'<h2>內容</h2><ul>' + "".join(f"<li>{esc(x)}</li>" for x in s["detail"]) + "</ul>"
                f'<h2>適合誰</h2><p>{esc(s["who"])}</p>'
                f'<h2>時間</h2><p>{esc(s["timing"])}</p>'
                f'<h2>費用</h2><p>{price}</p>'
                f'<h2>怎麼登記</h2><p>私訊本宮官方 LINE 或臉書粉專，或親至{esc(t["name"])}登記，也可以來電 {esc(t["phone"])}。</p>'
                f'<p class="muted"><a href="./">← 看本宮所有服務</a>｜<a href="nianli.html">年度祭典</a></p>')
        title = f'{s["name"]}｜{t["name"]}（新北中和）'
        desc = f'{t["name"]}{s["name"]}：{s["summary"]}{s["timing"]}'
        ld = {"@context": "https://schema.org", "@type": "Service", "name": s["name"], "description": s["summary"],
              "areaServed": "新北市中和區", "provider": temple_ld(t, base)}
        (out / f'{s["slug"]}.html').write_text(page(t, title, desc, body, url, ld), encoding="utf-8")

    # 年度祭典頁（只列固定農曆換算的國曆；法會日期未公告就寫「依公告」）
    rows = ""
    for y in d["yearly"]:
        sol = "公告後更新"
        if y.get("solar"):
            day = dt.date.fromisoformat(y["solar"])
            sol = f"{day.month}/{day.day}（{WEEK[day.weekday()]}）" + ("" if day.year == 2027 else f"，{day.year}")
        rows += f'<tr><td>{esc(y["lunar"])}</td><td>{sol}</td><td>{esc(y["name"])}' + (f'<br><span class="muted">{esc(y["note"])}</span>' if y.get("note") else "") + "</td></tr>"
    url = base + "nianli.html"
    urls.append(url)
    body = (f'<h1>{esc(d["year_label"])}年度祭典與法會</h1><p class="lead">本宮每年固定辦理的神明聖誕與法會。歡迎回宮參拜。</p>'
            f'<table><tr><th>農曆</th><th>國曆</th><th>祭典</th></tr>{rows}</table>'
            f'<p class="muted">法會日期每年請示後公告；國曆日期為農曆換算，以本宮公告為準。</p><p class="muted"><a href="./">← 看本宮所有服務</a></p>')
    (out / "nianli.html").write_text(page(t, f'{d["year_label"]}年度祭典與法會｜{t["name"]}', f'{t["name"]}{d["year_label"]}神明聖誕、點燈、祭改、普渡、禮斗等年度祭典一覽。', body, url), encoding="utf-8")

    # 總覽頁
    groups = {}
    for s in d["services"]:
        groups.setdefault(s["group"], []).append(s)
    body = (f'<h1>{esc(t["name"])}・祈福服務</h1><p class="lead">位於新北市中和區興南路三段，主祀{esc(t["deity"])}。'
            '點燈、安太歲、祭改、普渡、禮斗，歡迎十方善信回宮祈福。</p>')
    for g, items in groups.items():
        body += f"<h2>{esc(g)}</h2>" + "".join(f'<div class="card"><a href="{esc(s["slug"])}.html"><b>{esc(s["name"])}</b>｜{esc(s["summary"])}</a></div>' for s in items)
    body += '<h2>年度祭典</h2><div class="card"><a href="nianli.html"><b>年度祭典與法會一覽</b>｜神明聖誕、法會時間</a></div>'
    (out / "index.html").write_text(page(t, f'{t["name"]}｜新北中和 點光明燈・安太歲・普渡・禮斗', f'{t["name"]}位於新北市中和區，主祀{t["deity"]}，受理光明燈、安太歲、財庫燈、新春祭改、中元普渡、祈安禮斗法會。', body, base, temple_ld(t, base)), encoding="utf-8")

    sm = "".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)
    (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>', encoding="utf-8")
    return len(urls)
