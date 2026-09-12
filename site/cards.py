#!/usr/bin/env python3
"""
ilsvotentquoi.fr — cartes de partage, rendues depuis un gabarit HTML (mêmes polices que le site).

    python site/cards.py                 # tout : og (1200×630) + carré (1080×1080) pour chaque vote,
                                         #        story (1080×1920) pour les textes entiers et motions
    python site/cards.py --limit 20      # test
    python site/cards.py --formats og    # seulement le format lien

Sortie : dist/og/<n>.png, dist/og/<n>-carre.png, dist/og/<n>-story.png
Nécessite : pip install playwright && playwright install chromium
"""
import html, json, math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "data", "site.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "dist", "og"); os.makedirs(OUT, exist_ok=True)
ORDER = ["LFI", "GDR", "ECO", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDR", "RN", "NI"]
COL = {g["id"]: g["couleur"] for g in D["groupes"]}
TX, DEPS = D["textes"], D["deputes"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
esc = lambda s: html.escape(str(s), quote=True)

def fdate(d): y, m, dd = d.split("-"); return f"{int(dd)} {MONTHS[int(m)-1]} {y}"
def clean_title(t): return re.sub(r"\s*\((première|deuxième|nouvelle|troisième)[^)]*\)\.?$", "", t).rstrip(".")
def headline(s):
    """La question, comme les gens la tapent."""
    if s["k"] == "a" and s.get("a"):
        a = s["a"]; return f"Qui a voté l'amendement de {a['au']}" + (f" ({a['gr']})" if a["gr"] else "") + " ?", TX[s["tx"]]
    t = re.sub(r"\s*\([^)]*\)\s*$", "", clean_title(s["ti"])); t = t[0].lower() + t[1:]
    t = re.sub(r"^l'ensemble (de |du |d')", lambda m: {"de ": "", "du ": "le ", "d'": "l'"}[m.group(1)], t)
    return ("Qui a voté pour " if s["s"] else "Qui a voté contre ") + t + " ?", None
def group_at(dep, date):
    g = dep["g"][0][1]
    for d, gi in dep["g"]:
        if d <= date: g = gi
    return ORDER[g]
def seats(n=577, rows=11, cx=300, cy=290, r0=95, r1=280):
    rad = [r0 + (r1 - r0) * i / (rows - 1) for i in range(rows)]; tot = sum(rad); out = []; left = n
    for i, r in enumerate(rad):
        k = left if i == rows - 1 else round(n * r / tot); left -= k
        for j in range(k):
            a = math.pi * (0.5 if k == 1 else j / (k - 1)); out.append((cx - math.cos(a) * r, cy - math.sin(a) * r, a))
    out.sort(key=lambda p: p[2]); return out
SEATS = seats()
def people(s):
    v, date = s["vote"], s["d"]; out = []
    for i, d in enumerate(DEPS):
        vote = v[i] if i < len(v) else "."
        if vote == "." and not (d["f"] and d["l"] and d["f"] <= date <= d["l"]): continue
        out.append((group_at(d, date), vote, d["nom"]))
    out.sort(key=lambda p: (ORDER.index(p[0]), p[2])); return out

def hemi_svg(s):
    dots = []
    for k, (g, vote, _) in enumerate(people(s)[:577]):
        x, y, _ = SEATS[k]; c = COL[g]; x, y = f"{x:.1f}", f"{y:.1f}"
        if vote == "P": dots.append(f'<circle cx="{x}" cy="{y}" r="6.4" fill="{c}"/>')
        elif vote == "C": dots.append(f'<circle cx="{x}" cy="{y}" r="6.4" fill="{c}"/><path d="M{float(x)-2.7} {float(y)-2.7}l5.4 5.4M{float(x)+2.7} {float(y)-2.7}l-5.4 5.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>')
        elif vote == "A": dots.append(f'<circle cx="{x}" cy="{y}" r="6.4" fill="url(#h-{g})"/>')
        else: dots.append(f'<circle cx="{x}" cy="{y}" r="6.4" fill="#fff" stroke="{c}" stroke-width="1.3"/>')
    defs = "".join(f'<pattern id="h-{g}" patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)"><rect width="4" height="4" fill="{COL[g]}"/><rect width="2" height="4" fill="#fff" opacity=".75"/></pattern>' for g in ORDER)
    return f'<svg viewBox="0 0 600 300" xmlns="http://www.w3.org/2000/svg"><defs>{defs}</defs>{"".join(dots)}</svg>'

CSS = """
*{box-sizing:border-box;margin:0}
html,body{width:100%;height:100%;background:#fff;color:#000;font-family:"Public Sans","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
.card{width:100%;height:100%;display:flex;flex-direction:column;padding:64px;position:relative;overflow:hidden}
.card::before{content:"";position:absolute;left:0;top:0;right:0;height:12px;background:#000}
.kicker{font-size:22px;letter-spacing:.12em;text-transform:uppercase;color:#828282;font-weight:600}
.kicker b{color:#B91D47}
h1{font-family:"Newsreader",Georgia,serif;font-weight:700;letter-spacing:-.015em;line-height:1.05;margin-top:18px;text-wrap:balance}
.sub{font-size:24px;color:#555;margin-top:14px;line-height:1.3}
.hemi{margin:auto 0;width:100%}
.hemi svg{display:block;width:100%;height:auto}
.res{display:flex;align-items:center;gap:22px;flex-wrap:wrap}
.pill{font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#fff;background:#1E7A4A;border-radius:999px;padding:12px 26px;font-size:24px}
.pill.no{background:#B91D47}
.tally{font-size:30px;font-variant-numeric:tabular-nums}
.tally b{font-weight:700}
.tally span{color:#828282;margin:0 6px}
.leg{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:20px;font-weight:600;margin-top:22px}
.leg i{display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:8px;vertical-align:-1px}
.tex{font-size:19px;color:#828282;margin-top:12px}
.brand{display:flex;justify-content:space-between;align-items:baseline;margin-top:26px;border-top:2px solid #000;padding-top:16px}
.brand b{font-family:"Newsreader",Georgia,serif;font-size:32px;font-weight:700;letter-spacing:-.01em}
.brand b em{font-style:normal;font-weight:300}
.brand span{font-size:19px;color:#828282}
/* formats */
.og{--w:1200px;--h:630px}
.og .card{padding:44px 56px;flex-direction:row;gap:40px}
.og .left{flex:1 1 52%;display:flex;flex-direction:column}
.og .right{flex:1 1 48%;display:flex;flex-direction:column;justify-content:center}
.og h1{font-size:46px}
.og .sub{font-size:19px;margin-top:8px}
.og .res{margin-top:auto}
.og .pill{font-size:17px;padding:8px 18px}
.og .tally{font-size:22px}
.og .leg{font-size:15px;gap:6px 14px;margin-top:14px}
.og .leg i{width:11px;height:11px;margin-right:6px}
.og .brand{margin-top:14px;padding-top:10px}
.og .brand b{font-size:24px}
.og .brand span{font-size:15px}
.og .tex{display:none}
.carre h1{font-size:58px}
.carre .hemi{margin:34px 0 auto}
.story .card{padding:90px 72px}
.story h1{font-size:74px}
.story .sub{font-size:30px}
.story .hemi{margin:60px 0 auto}
.story .pill{font-size:30px;padding:16px 34px}
.story .tally{font-size:38px}
.story .leg{font-size:26px;gap:12px 26px;margin-top:34px}
.story .leg i{width:18px;height:18px}
.story .tex{font-size:24px}
.story .brand b{font-size:44px}
.story .brand span{font-size:24px}
"""
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:wght@300;700&family=Public+Sans:wght@400;600;700&display=swap">'

def card_html(s, fmt):
    q, tx = headline(s); ok = s["s"] == 1
    present = {g[0] for g in s["g"]}
    leg = "".join(f'<span><i style="background:{COL[g]}"></i>{g}</span>' for g in ORDER if g in present)
    res = f'<div class="res"><span class="pill {"" if ok else "no"}">{"Adopté" if ok else "Rejeté"}</span><span class="tally"><b>{s["t"][0]}</b> pour<span>·</span><b>{s["t"][1]}</b> contre<span>·</span><b>{s["t"][2]}</b> abst.</span></div>'
    tex = '<p class="tex">● pour &nbsp; ⊗ contre &nbsp; ▨ abstention &nbsp; ○ absent &nbsp;·&nbsp; couleur = groupe</p>'
    brand = f'<div class="brand"><b>Ils votent <em>quoi</em> ?</b><span>ilsvotentquoi.fr · source : Assemblée nationale</span></div>'
    kicker = f'<p class="kicker"><b>Assemblée nationale</b> · {fdate(s["d"])} · scrutin nº {s["n"]}</p>'
    sub = f'<p class="sub">{esc(tx)}</p>' if tx else ""
    if fmt == "og":
        body = f'<div class="card"><div class="left">{kicker}<h1>{esc(q)}</h1>{sub}{res}<div class="leg">{leg}</div>{brand}</div><div class="right"><div class="hemi">{hemi_svg(s)}</div></div></div>'
    else:
        body = f'<div class="card">{kicker}<h1>{esc(q)}</h1>{sub}<div class="hemi">{hemi_svg(s)}</div>{res}<div class="leg">{leg}</div>{tex}{brand}</div>'
    return f'<!doctype html><html lang="fr" class="{fmt}"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{body}</body></html>'

SIZES = {"og": (1200, 630), "carre": (1080, 1080), "story": (1080, 1920)}

def main():
    from playwright.sync_api import sync_playwright
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    formats = sys.argv[sys.argv.index("--formats") + 1].split(",") if "--formats" in sys.argv else ["og", "carre", "story"]
    todo = [s for s in sorted(D["scrutins"], key=lambda s: -s["n"]) if s["g"]][:limit]
    with sync_playwright() as p:
        b = p.chromium.launch(); pages = {}
        for fmt, (w, h) in SIZES.items():
            if fmt in formats: pages[fmt] = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        for i, s in enumerate(todo):
            for fmt, page in pages.items():
                if fmt == "story" and s["k"] not in ("e", "m"): continue          # story : textes entiers et motions
                if fmt == "carre" and s["k"] not in ("e", "m") and s["v"] < 200: continue   # carré : votes suivis
                page.set_content(card_html(s, fmt), wait_until="load")
                if i == 0: page.wait_for_timeout(1500)   # laisser les polices arriver la première fois
                name = f"{s['n']}.png" if fmt == "og" else f"{s['n']}-{fmt}.png"
                page.screenshot(path=os.path.join(OUT, name), type="png")
            if i % 500 == 0: print(f"{i}/{len(todo)}", file=sys.stderr, flush=True)
        # image par défaut du site
        pg = b.new_page(viewport={"width": 1200, "height": 630})
        pg.set_content(f'<!doctype html><html class="og"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body><div class="card" style="flex-direction:column;justify-content:center;align-items:center;text-align:center"><h1 style="font-size:84px">Ils votent <span style="font-weight:300">quoi</span> ?</h1><p class="sub" style="font-size:26px;margin-top:18px">Les votes réels de chaque groupe et de chaque député, sujet par sujet</p><p class="tex" style="display:block;margin-top:40px">ilsvotentquoi.fr · source : Assemblée nationale</p></div></body></html>')
        pg.wait_for_timeout(1000); pg.screenshot(path=os.path.join(ROOT, "dist", "static", "og-default.png"))
        b.close()

if __name__ == "__main__": main()
