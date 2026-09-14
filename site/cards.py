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
    """Titre court + accroche. Texte entier : le titre du dossier (court) ; motion : qui l'a déposée."""
    ok = s["s"] == 1; tx = TX[s["tx"]]; ti = s["ti"]
    if s["k"] == "a" and s.get("a"):
        a = s["a"]; return "Qui a voté l'amendement ?", f"Amendement de {a['au']}" + (f" ({a['gr']})" if a["gr"] else ""), tx
    if s["k"] == "m":
        who = re.search(r"par (?:MM\.|Mmes|M\.|Mme) ([^,]+?)(?:,| et | du | de la | des |\.$|$)", ti)
        who = who.group(1).strip() if who else ""
        if "censure" in ti.lower():
            return ("Qui a voté la censure ?", "Motion de censure" + (f" déposée par {who}" if who else ""),
                    f"{'Adoptée' if ok else 'Rejetée'} : {s['t'][0]} voix, il en fallait 289")
        return "Qui a voté le rejet ?", "Motion de rejet préalable" + (f" de {who}" if who else ""), tx
    if s["k"] == "a":
        t = clean_title(ti); return "Qui a voté l'amendement ?", t[0].upper() + t[1:], tx
    t = tx if len(tx) < 200 else clean_title(ti)
    t = t[0].upper() + t[1:]
    return ("Qui a voté pour ?" if ok else "Qui a voté contre ?"), t, None

def positions(s):
    """Accroche mécanique : la position majoritaire de chaque groupe."""
    by = {"pour": [], "contre": [], "abstention": [], "absent": []}
    for g in s["g"]:
        if g[0] == "NI": continue
        pos = "absent" if g[1]+g[2]+g[3] == 0 else max((("pour", g[1]), ("contre", g[2]), ("abstention", g[3])), key=lambda x: x[1])[0]
        by[pos].append(g[0])
    for k in by: by[k].sort(key=ORDER.index)
    chips = lambda gs: "".join(f'<span class="chip"><i style="background:{COL[g]}"></i>{g}</span>' for g in gs)
    out = []
    for k, l in [("pour", "Pour"), ("contre", "Contre"), ("abstention", "Abstention"), ("absent", "Absent")]:
        if by[k]: out.append(f'<div class="pos"><span class="pl">{l}</span>{chips(by[k])}</div>')
    return '<div class="positions">' + "".join(out) + "</div>"
def has_card(s):
    """Une carte pour les textes entiers, les motions et les amendements suivis (200 votants ou plus)."""
    return s["k"] in ("e", "m") or s["v"] >= 200

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
.q{font-family:"Newsreader",Georgia,serif;font-weight:300;font-size:34px;color:#B91D47;margin-top:22px;letter-spacing:-.01em}
.positions{display:flex;flex-direction:column;gap:8px;margin-top:18px}
.pos{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:22px}
.pl{font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:17px;color:#000;width:150px}
.chip{display:inline-flex;align-items:center;gap:6px;border:1.5px solid #000;border-radius:999px;padding:4px 12px 4px 8px;font-weight:700;font-size:19px}
.chip i{width:12px;height:12px;border-radius:50%;display:inline-block}
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
.og .q{font-size:24px;margin-top:10px}
.og h1{font-size:38px;margin-top:6px}
.og .positions{gap:5px;margin-top:12px}
.og .pl{font-size:13px;width:105px}
.og .chip{font-size:14px;padding:2px 9px 2px 6px}
.og .chip i{width:9px;height:9px}
.og .pos{font-size:15px}
.carre h1{font-size:50px;margin-top:6px}
.carre h1.long{font-size:42px}
.carre .hemi{margin:auto 0}
.story .card{padding:90px 72px}
.story h1{font-size:66px;margin-top:8px}
.story h1.long{font-size:54px}
.story .q{font-size:46px;margin-top:40px}
.story .positions{gap:12px;margin-top:34px}
.story .pos{font-size:30px}
.story .pl{font-size:22px;width:200px}
.story .chip{font-size:26px;padding:6px 16px 6px 10px}
.story .chip i{width:16px;height:16px}
.story .sub{font-size:30px}
.story .hemi{margin:auto 0}
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
    q, t1, tx = headline(s); ok = s["s"] == 1
    present = {g[0] for g in s["g"]}
    leg = "".join(f'<span><i style="background:{COL[g]}"></i>{g}</span>' for g in ORDER if g in present)
    res = f'<div class="res"><span class="pill {"" if ok else "no"}">{"Adopté" if ok else "Rejeté"}</span><span class="tally"><b>{s["t"][0]}</b> pour<span>·</span><b>{s["t"][1]}</b> contre<span>·</span><b>{s["t"][2]}</b> abst.</span></div>'
    tex = '<p class="tex">● pour &nbsp; ⊗ contre &nbsp; ▨ abstention &nbsp; ○ absent &nbsp;·&nbsp; couleur = groupe</p>'
    brand = f'<div class="brand"><b>Ils votent <em>quoi</em> ?</b><span>ilsvotentquoi.fr · source : Assemblée nationale</span></div>'
    kicker = f'<p class="kicker"><b>Assemblée nationale</b> · {fdate(s["d"])} · scrutin nº {s["n"]}</p>'
    h1 = f'<h1 class="{"long" if len(t1) > 90 else ""}">{esc(t1)}</h1>'
    sub = f'<p class="sub">{esc(tx)}</p>' if tx else ""
    qq = f'<p class="q">{esc(q)}</p>'
    if fmt == "og":
        body = f'<div class="card"><div class="left">{kicker}{qq}{h1}{sub}{positions(s)}{res}{brand}</div><div class="right"><div class="hemi">{hemi_svg(s)}</div></div></div>'
    else:
        body = f'<div class="card">{kicker}{qq}{h1}{sub}<div class="hemi">{hemi_svg(s)}</div>{res}{positions(s)}{tex}{brand}</div>'
    return f'<!doctype html><html lang="fr" class="{fmt}"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{body}</body></html>'

GN = {g["id"]: g["nom"] for g in D["groupes"]}
def group_pos(g):
    if g[1] + g[2] + g[3] == 0: return "absent"
    x = max(g[1], g[2], g[3]); return "pour" if x == g[1] else "contre" if x == g[2] else "abstention"

GCSS = """
.g h1{margin-top:14px}
.g .lead{font-size:26px;color:#555;margin-top:16px;line-height:1.35;max-width:34ch}
.tiles{display:grid;grid-template-columns:repeat(2,1fr);gap:22px;margin:auto 0}
.tile{border-top:3px solid #000;padding-top:14px}
.tile b{display:block;font-family:"Newsreader",Georgia,serif;font-size:118px;line-height:.95;letter-spacing:-.03em;font-weight:700}
.tile span{display:block;font-size:24px;font-weight:600;margin-top:10px}
.tile small{display:block;font-size:19px;color:#828282;margin-top:4px}
.bar{display:flex;height:34px;border:2px solid #000;margin-top:10px;overflow:hidden}
.bar i{display:block;height:100%}
.dot{display:inline-block;width:.75em;height:.75em;border-radius:50%;vertical-align:-.05em;margin-right:.3em}
.head{display:flex;gap:28px;align-items:flex-start;margin-top:14px}
.head h1{margin-top:0}
.pic{width:150px;height:192px;object-fit:cover;border:3px solid #000;flex:none}
.og .head{gap:20px}
.og .pic{width:100px;height:128px}
.story .pic{width:210px;height:269px}
.story .g .lead{font-size:32px}
.story .tiles{gap:40px 28px}
.story .tile b{font-size:170px}
.story .tile span{font-size:32px}
.story .tile small{font-size:24px}
.story .bar{height:48px}
.og .card.g{flex-direction:column;padding:36px 56px}
.og .g .kicker{font-size:15px}
.og .g h1{font-size:40px}
.og .g .brand{margin-top:14px}
.og .tiles{grid-template-columns:repeat(4,1fr);gap:18px;margin:auto 0 0}
.og .tile b{font-size:72px}
.og .tile span{font-size:17px}
.og .tile small{font-size:14px}
.og .g .lead{font-size:18px;max-width:none}
.og .bar{height:22px}
"""

def group_card_html(gid, fmt):
    ess = [s for s in D["scrutins"] if s["k"] in ("e", "m")]
    c = {"pour": 0, "contre": 0, "abstention": 0, "absent": 0}; rows = []
    for s in ess:
        g = next((x for x in s["g"] if x[0] == gid), None)
        if g: c[group_pos(g)] += 1; rows.append(g)
    n = sum(c.values()); col = COL[gid]
    part = sum(g[1]+g[2]+g[3] for g in rows) / max(1, sum(g[5] for g in rows))
    pct = lambda k: f"{round(100*c[k]/max(1,n))} %"
    tex = {"pour": f"background:{col}", "contre": f"background:repeating-linear-gradient(-45deg,{col} 0 4px,#fff 4px 8px)",
           "abstention": f"background:repeating-linear-gradient(45deg,{col} 0 3px,#fff 3px 8px)", "absent": "background:#fff"}
    tiles = "".join(f'<div class="tile"><b>{c[k]}</b><span><i class="dot" style="{tex[k]};border:2px solid {col}"></i>{l}</span><small>{pct(k)} des votes décisifs</small></div>'
                    for k, l in [("pour", "fois pour"), ("contre", "fois contre"), ("abstention", "abstentions"), ("absent", "absent")])
    bar = '<div class="bar">' + "".join(f'<i style="width:{100*c[k]/max(1,n):.1f}%;{tex[k]}"></i>' for k in ("pour","contre","abstention","absent")) + "</div>"
    name = GN[gid]; q = f"{name} : ils votent quoi ?"
    lead = f"Position majoritaire du groupe <b style=\"color:{col}\">{gid}</b> sur les <b>{n} votes décisifs</b> de la législature : lois entières, motions de rejet, motions de censure. Présence moyenne : <b>{round(100*part)} %</b>."
    kicker = f'<p class="kicker"><b>Assemblée nationale</b> · 17ᵉ législature · votes décisifs</p>'
    brand = '<div class="brand"><b>Ils votent <em>quoi</em> ?</b><span>ilsvotentquoi.fr · source : Assemblée nationale</span></div>'
    body = f'<div class="card g" style="--c:{col}">{kicker}<h1><i class="dot" style="background:{col};width:.55em;height:.55em"></i>{esc(q)}</h1><p class="lead">{lead}</p><div class="tiles">{tiles}</div>{bar}{brand}</div>'
    return f'<!doctype html><html lang="fr" class="{fmt}"><head><meta charset="utf-8">{FONTS}<style>{CSS}{GCSS}</style></head><body>{body}</body></html>'

def deputy_card_html(i, d, fmt):
    """Carte d'un député : présence, votes décisifs, écarts avec son groupe. Chiffres bruts."""
    LBL = {"P": "pour", "C": "contre", "A": "abstention"}
    ess = {"pour": 0, "contre": 0, "abstention": 0, "absent": 0}; present = eligible = ecarts = 0
    for s in D["scrutins"]:
        v = s["vote"][i] if i < len(s["vote"]) else "."
        inm = d["f"] <= s["d"] <= d["l"]
        if inm: eligible += 1
        if v in "PCA": present += 1
        if s["k"] in ("e", "m") and inm: ess[LBL[v] if v in "PCA" else "absent"] += 1
        if v in "PCA":
            gid = group_at(d, s["d"]); g = next((x for x in s["g"] if x[0] == gid), None)
            if g and gid != "NI":
                gp = group_pos(g)
                if gp != "absent" and gp != LBL[v]: ecarts += 1
    gid = ORDER[d["g"][-1][1]]; col = COL[gid]; n = sum(ess.values())
    med = json.load(open(os.path.join(ROOT, "dist", "api", "medianes.json"))) if os.path.exists(os.path.join(ROOT, "dist", "api", "medianes.json")) else {"presence": 23, "presence_essentiel": 43}
    ess_rate = round(100 * (n - ess["absent"]) / max(1, n))
    rate = round(100 * present / max(1, eligible)); pe = (f"{100 * ecarts / max(1, present):.1f}".replace(".", ",") if ecarts and 100 * ecarts / present < 1 else str(round(100 * ecarts / max(1, present))))
    tex = {"pour": f"background:{col}", "contre": f"background:repeating-linear-gradient(-45deg,{col} 0 4px,#fff 4px 8px)",
           "abstention": f"background:repeating-linear-gradient(45deg,{col} 0 3px,#fff 3px 8px)", "absent": "background:#fff"}
    tiles = "".join(f'<div class="tile"><b>{ess[k]}</b><span><i class="dot" style="{tex[k]};border:2px solid {col}"></i>{l}</span><small>sur {n} votes décisifs</small></div>'
                    for k, l in [("pour", "pour"), ("contre", "contre"), ("abstention", "abstentions"), ("absent", "absent")])
    bar = '<div class="bar">' + "".join(f'<i style="width:{100*ess[k]/max(1,n):.1f}%;{tex[k]}"></i>' for k in ("pour","contre","abstention","absent")) + "</div>"
    where = (d["dept"] + (f", {d['circo']}ᵉ circonscription" if d["circo"] else "")) if d["dept"] else ""
    lead = f"<b style=\"color:{col}\">{gid}</b>{' · ' + esc(where) if where else ''}. Présence : <b>{rate} %</b> tous scrutins (médiane des députés {med["presence"]} %), <b>{ess_rate} %</b> sur les votes décisifs (médiane {med["presence_essentiel"]} %). A voté autrement que la majorité de son groupe <b>{ecarts} fois</b> ({pe} % de ses votes)."
    kicker = '<p class="kicker"><b>Assemblée nationale</b> · 17ᵉ législature · votes décisifs</p>'
    brand = '<div class="brand"><b>Ils votent <em>quoi</em> ?</b><span>ilsvotentquoi.fr · source : Assemblée nationale</span></div>'
    photo = os.path.join(ROOT, "data", "raw", "photos", d["id"] + ".jpg"); pic = ""
    if os.path.exists(photo):
        import base64
        pic = f'<img class="pic" src="data:image/jpeg;base64,{base64.b64encode(open(photo, "rb").read()).decode()}" style="border-color:{col}">'
    body = f'<div class="card g">{kicker}<div class="head">{pic}<div><h1><i class="dot" style="background:{col};width:.55em;height:.55em"></i>{esc(d["nom"])} : que vote-t-{"elle" if d["nom"].startswith("Mme") else "il"} ?</h1><p class="lead">{lead}</p></div></div><div class="tiles">{tiles}</div>{bar}{brand}</div>'
    return f'<!doctype html><html lang="fr" class="{fmt}"><head><meta charset="utf-8">{FONTS}<style>{CSS}{GCSS}</style></head><body>{body}</body></html>'

SIZES = {"og": (1200, 630), "carre": (1080, 1080), "story": (1080, 1920)}

def main():
    from playwright.sync_api import sync_playwright
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    formats = sys.argv[sys.argv.index("--formats") + 1].split(",") if "--formats" in sys.argv else ["og", "carre", "story"]
    todo = [s for s in sorted(D["scrutins"], key=lambda s: -s["n"]) if s["g"]][:limit]
    if "--groupes" in sys.argv: todo = []
    with sync_playwright() as p:
        b = p.chromium.launch(); pages = {}
        for fmt, (w, h) in SIZES.items():
            if fmt in formats: pages[fmt] = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        for i, s in enumerate(todo):
            if not has_card(s): continue   # limite Cloudflare Pages : 20 000 fichiers par site
            for fmt, page in pages.items():
                if fmt == "story" and s["k"] not in ("e", "m"): continue          # story : textes entiers et motions
                page.set_content(card_html(s, fmt), wait_until="load")
                if i == 0: page.wait_for_timeout(1500)   # laisser les polices arriver la première fois
                name = f"{s['n']}.png" if fmt == "og" else f"{s['n']}-{fmt}.png"
                page.screenshot(path=os.path.join(OUT, name), type="png")
            if i % 500 == 0: print(f"{i}/{len(todo)}", file=sys.stderr, flush=True)
        # cartes par groupe (votes décisifs)
        for gid in ORDER:
            for fmt, page in pages.items():
                page.set_content(group_card_html(gid, fmt), wait_until="load"); page.wait_for_timeout(300)
                page.screenshot(path=os.path.join(OUT, f"groupe-{gid.lower()}{'' if fmt=='og' else '-'+fmt}.png"), type="png")
        # cartes par député (lien + carré)
        for i, d in enumerate(DEPS):
            for fmt, page in pages.items():
                if fmt == "story": continue
                page.set_content(deputy_card_html(i, d, fmt), wait_until="load")
                page.screenshot(path=os.path.join(OUT, f"depute-{d['id']}{'' if fmt=='og' else '-'+fmt}.png"), type="png")
            if i % 100 == 0: print(f"députés {i}/{len(DEPS)}", file=sys.stderr, flush=True)
        # image par défaut du site
        pg = b.new_page(viewport={"width": 1200, "height": 630})
        pg.set_content(f'<!doctype html><html class="og"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body><div class="card" style="flex-direction:column;justify-content:center;align-items:center;text-align:center"><h1 style="font-size:84px">Ils votent <span style="font-weight:300">quoi</span> ?</h1><p class="sub" style="font-size:26px;margin-top:18px">Les votes réels de chaque groupe et de chaque député, sujet par sujet</p><p class="tex" style="display:block;margin-top:40px">ilsvotentquoi.fr · source : Assemblée nationale</p></div></body></html>')
        pg.wait_for_timeout(1000); pg.screenshot(path=os.path.join(ROOT, "dist", "static", "og-default.png"))
        b.close()

if __name__ == "__main__": main()
