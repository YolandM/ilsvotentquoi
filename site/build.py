#!/usr/bin/env python3
"""
ilsvotentquoi.fr — générateur de site statique.

    python site/build.py            # lit data/site.json, écrit dist/

Une page par scrutin, par sujet, par groupe, par groupe×sujet, par texte de loi, par député.
Tout est du HTML complet (lisible par Google et par les IA), le JavaScript n'ajoute que
l'hémicycle interactif et le tableau nominatif.
"""
import collections, datetime, html, json, math, os, re, shutil, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "site.json")
DIST = os.path.join(ROOT, "dist")
STATIC = os.path.join(ROOT, "site", "static")
SITE = "https://ilsvotentquoi.fr"
NAME = "Ils votent quoi ?"
ORDER = ["LFI", "GDR", "ECO", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDR", "RN", "NI"]
PER_PAGE = 30
THEME_LABEL = {"pouvoir-achat": "Pouvoir d'achat", "travail-retraites": "Travail & retraites", "fiscalite-riches": "Fiscalité du capital",
    "sante": "Santé", "education": "Éducation", "ecologie-energie": "Écologie & énergie", "agriculture-alimentation": "Agriculture & alimentation",
    "securite-justice": "Sécurité & justice", "immigration": "Immigration", "logement-territoires": "Logement & territoires",
    "economie-entreprises": "Économie & budget", "institutions-libertes": "Institutions & libertés", "egalite-droits": "Égalité & droits",
    "international-defense": "International & défense", "outre-mer": "Outre-mer", "culture-sport-medias": "Culture, sport, médias"}
KIND = {"a": "Amendement", "e": "Texte entier", "r": "Article", "m": "Motion", "u": "Vote"}
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

def esc(s): return html.escape(str(s if s is not None else ""), quote=True)
def norm(s): return re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode())
def slug(s, n=70): return re.sub(r"\s+", "-", norm(s).strip())[:n].rstrip("-")
def fdate(d): y, m, dd = d.split("-"); return f"{int(dd)}{'er' if dd=='01' else ''} {MONTHS[int(m)-1]} {y}"
def clean_title(t):
    t = re.sub(r"\s*\((première|deuxième|nouvelle|troisième)[^)]*\)\.?$", "", t).rstrip(".")
    return t[0].upper() + t[1:]
def write(path, content):
    full = os.path.join(DIST, path.lstrip("/"))
    if full.endswith("/"): full += "index.html"
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f: f.write(content)

# ----------------------------------------------------------------------------- données
D = json.load(open(DATA, encoding="utf-8"))
TX, S, DEPS, GROUPS = D["textes"], D["scrutins"], D["deputes"], {g["id"]: g for g in D["groupes"]}
COL = {g: GROUPS[g]["couleur"] for g in GROUPS}
GN = {g: GROUPS[g]["nom"] for g in GROUPS}
for s in S:
    s["gm"] = {g[0]: {"id": g[0], "pour": g[1], "contre": g[2], "abstention": g[3], "nonVotant": g[4], "membres": g[5], "absent": max(g[5]-g[1]-g[2]-g[3]-g[4], 0)} for g in s["g"]}
    s["url"] = f"/vote/{s['n']}-{slug(TX[s['tx']], 50)}/"
    s["title"] = short_title = None
S_BY_N = {s["n"]: s for s in S}
DEP_BY_I = {i: d for i, d in enumerate(DEPS)}
for i, d in enumerate(DEPS): d["url"] = f"/depute/{d['slug']}-{d['id']}/"
import hashlib
def _asset_v(name):
    try: return hashlib.md5(open(os.path.join(STATIC, name), "rb").read()).hexdigest()[:8]
    except Exception: return "0"
CSS_V, JS_V = _asset_v("style.css"), _asset_v("hemi.js")
BUILD_DATE = datetime.date.today().isoformat()
try:
    from zoneinfo import ZoneInfo; _now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
except Exception: _now = datetime.datetime.now()
BUILD_STAMP = f"{fdate(_now.date().isoformat())} à {_now.strftime('%Hh%M')}"
LAST_VOTE = max(s["d"] for s in S)

def title_of(s):
    """Titre lisible. Amendement : auteur + texte ; sinon intitulé officiel nettoyé."""
    if s["k"] == "a" and s.get("a"):
        a = s["a"]; who = a["au"] + (f" ({a['gr']})" if a["gr"] else "")
        return f"Amendement de {who} · {TX[s['tx']]}"
    if s["k"] == "m":
        who = re.search(r"par (?:MM\.|Mmes|M\.|Mme) ([^,]+?)(?:,| et | du | de la | des |\.$|$)", s["ti"])
        who = who.group(1).strip() if who else ""
        if "censure" in s["ti"].lower(): return "Motion de censure" + (f" déposée par {who}" if who else "")
        return "Motion de rejet préalable" + (f" de {who}" if who else "") + f" · {TX[s['tx']]}"
    return clean_title(s["ti"])

def has_card(s):
    """Même règle que site/cards.py : carte pour les textes entiers, motions et amendements à 200 votants ou plus."""
    return s["k"] in ("e", "m") or s["v"] >= 200

def group_pos(g):
    if g["pour"] + g["contre"] + g["abstention"] == 0: return "absent"
    x = max(g["pour"], g["contre"], g["abstention"])
    return "pour" if x == g["pour"] else "contre" if x == g["contre"] else "abstention"

def sentence(s):
    """Phrase factuelle, générée, pour les moteurs et les IA."""
    res = "adopté" if s["s"] else "rejeté"
    what = title_of(s); what = what[0].lower() + what[1:]
    if s["k"] == "a": what = f"l'{s['ti'][2:]}" if s["ti"].lower().startswith("l'") else s["ti"]
    if s["k"] == "m": what = "la " + what.split(" · ")[0]
    base = f"Le {fdate(s['d'])}, l'Assemblée nationale a <b>{res}</b> {esc(what.rstrip('.'))} par <b>{s['t'][0]} voix pour</b>, <b>{s['t'][1]} contre</b> et <b>{s['t'][2]} abstentions</b> ({s['v']} votants sur 577)."
    by = {"pour": [], "contre": [], "abstention": [], "absent": []}
    for gid in ORDER:
        g = s["gm"].get(gid)
        if not g: continue
        p = group_pos(g); n = {"pour": g["pour"], "contre": g["contre"], "abstention": g["abstention"], "absent": g["absent"]+g["nonVotant"]}[p]
        by[p].append(f"{gid} ({n}/{g['membres']})")
    parts = []
    if by["pour"]: parts.append("Ont voté pour, en majorité : " + ", ".join(by["pour"]))
    if by["contre"]: parts.append("Contre : " + ", ".join(by["contre"]))
    if by["abstention"]: parts.append("Abstention : " + ", ".join(by["abstention"]))
    if by["absent"]: parts.append("Absents ou non-votants en majorité : " + ", ".join(by["absent"]))
    return base + " " + ". ".join(parts) + "."

# ----------------------------------------------------------------------------- composants
def group_table(s):
    gs = [s["gm"][g] for g in ORDER if g in s["gm"]]
    if not gs: return ""
    mx = max(g["membres"] for g in gs)
    def xpat(c):
        svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='7' height='7'><rect width='7' height='7' fill='{c}'/><path d='M1.5 1.5l4 4M5.5 1.5l-4 4' stroke='white' stroke-width='1.2'/></svg>"
        from urllib.parse import quote
        return f"url('data:image/svg+xml,{quote(svg, safe='')}')"
    rows = []
    for g in gs:
        c = COL[g["id"]]; abs_ = g["absent"] + g["nonVotant"]; W = 100 * g["membres"] / mx
        seg = lambda n, st: f'<i style="width:{100*n/g["membres"]:.2f}%;{st}"></i>' if n > 0 else ""
        bar = (f'<div class="sb" style="width:{W:.2f}%">{seg(g["pour"], f"background:{c}")}{seg(g["contre"], f"background-image:{xpat(c)}")}'
               f'{seg(g["abstention"], f"background:repeating-linear-gradient(45deg,{c} 0 2.5px,#fff 2.5px 5px)")}{seg(abs_, f"background:#fff;box-shadow:inset 0 0 0 1px {c}")}</div>')
        cell = lambda v: f'<div class="c {"" if v else "z"}">{f"<b>{v}</b>" if v else "0"}</div>'
        rows.append(f'<div class="r"><div class="n"><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{c};margin-right:6px"></span><a href="/groupe/{g["id"].lower()}/" style="text-decoration:none">{g["id"]}</a><small>{esc(GN[g["id"]])} · {g["membres"]} membres</small></div><div class="b">{bar}</div>{cell(g["pour"])}{cell(g["contre"])}{cell(g["abstention"])}{cell(abs_)}</div>')
    return f'<div class="gt"><div class="r h"><div class="n">Groupe</div><div class="b">Répartition des membres</div><div>Pour</div><div>Contre</div><div>Abst.</div><div>Abs.</div></div>{"".join(rows)}</div>'

def mini_bar(s):
    """Une bande : chaque groupe à sa taille, coloré selon sa position majoritaire."""
    gs = [s["gm"][g] for g in ORDER if g in s["gm"]]; tot = sum(g["membres"] for g in gs)
    if not tot: return ""
    out = []
    for g in gs:
        p = group_pos(g); c = COL[g["id"]]; w = 100 * g["membres"] / tot
        st = {"pour": f"background:{c}", "contre": f"background:repeating-linear-gradient(-45deg,{c} 0 2px,#fff 2px 4px)",
              "abstention": f"background:repeating-linear-gradient(45deg,{c} 0 2px,#fff 2px 5px);opacity:.8", "absent": f"background:#fff;box-shadow:inset 0 0 0 1px {c}"}[p]
        out.append(f'<i style="width:{w:.2f}%;{st}" title="{esc(GN[g["id"]])} : {p}"></i>')
    return f'<div class="mini" aria-hidden="true">{"".join(out)}</div>'

def entry(s, compact=True):
    ok = s["s"] == 1
    why = ""
    if s.get("a") and s["a"]["ex"]:
        ex = esc(s["a"]["ex"]); short = (ex[:260].rsplit(" ", 1)[0] + "…") if len(ex) > 280 else ex
        why = f'<div class="why"><span class="lab">L\'auteur explique</span>« {short} »</div>'
    return f'''<article class="entry">
  <div class="cat"><span><b><a href="/sujet/{s['th'][0]}/" style="text-decoration:none;color:inherit">{THEME_LABEL[s['th'][0]]}</a></b> · {KIND.get(s['k'],'Vote')} · <time datetime="{s['d']}">{fdate(s['d'])}</time></span><span>Scrutin nº {s['n']}</span></div>
  <h3><a href="{s['url']}">{esc(title_of(s))}</a></h3>
  {f'<p class="off">{esc(clean_title(s["ti"]))}</p>' if s['k'] in ("a", "m") else ""}
  {why}
  <div class="result"><span class="pill {'ok' if ok else 'no'}">{'Adopté' if ok else 'Rejeté'}</span><span class="tally"><b>{s['t'][0]}</b> pour · <b>{s['t'][1]}</b> contre · <b>{s['t'][2]}</b> abst.</span><span>{s['v']} votants sur 577</span></div>
  {mini_bar(s)}
</article>'''

def layout(title, body, *, desc="", path="/", jsonld=None, og_image=None, current=None, extra_head=""):
    canonical = SITE + path
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    og = og_image or f"{SITE}/static/og-default.png"
    CUR = ' aria-current="page"'
    nav = "".join(f'<a href="{h}"{CUR if current==k else ""}>{l}</a>' for k, h, l in
                  [("votes", "/", "Les votes"), ("essentiels", "/essentiels/", "L'essentiel"), ("sujets", "/sujets/", "Par sujet"), ("groupes", "/groupes/", "Par groupe"), ("deputes", "/deputes/", "Par député"), ("methode", "/methode/", "Méthode"), ("recherche", "/recherche/", "Rechercher")])
    return f'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc[:300])}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article"><meta property="og:site_name" content="{NAME}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc[:200])}"><meta property="og:url" content="{canonical}"><meta property="og:image" content="{og}"><meta property="og:locale" content="fr_FR">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:image" content="{og}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,700;1,6..72,400&family=Public+Sans:wght@400;600;700&display=swap">
<link rel="stylesheet" href="/static/style.css?v={CSS_V}">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<script>window.IVQ={{colors:{json.dumps(COL)},names:{json.dumps(GN, ensure_ascii=False)}}};</script>
{ld}{extra_head}
</head>
<body>
<div class="topbar"><span>Assemblée nationale</span><span>17ᵉ législature</span><span>Scrutins publics</span><span>Dernier vote : {fdate(LAST_VOTE)}</span><span>Mis à jour le {BUILD_STAMP}</span></div>
<div class="masthead"><h1 class="brand"><a href="/" style="text-decoration:none">Ils votent <em>quoi</em> ?</a></h1><p class="tag">Les votes réels de chaque groupe et de chaque député, sujet par sujet</p></div>
<div class="subnav"><span class="mini" aria-hidden="true"><a href="/" style="text-decoration:none">Ils votent <em>quoi</em> ?</a></span>{nav}</div>
<div class="wrap">{body}</div>
<footer class="note" style="max-width:1180px;margin:48px auto 0;padding:16px 16px 40px"><p><b>{NAME}</b> — un outil indépendant et sans parti pris. Source : open data de l'Assemblée nationale, mis à jour chaque nuit. Chaque vote renvoie au scrutin officiel. <a href="/methode/">Méthode</a> · <a href="/llms.txt">Données pour les IA</a> · <a href="/sitemap.xml">Plan du site</a> · <a href="/statut/">Statut</a>. Site régénéré le {BUILD_STAMP} (heure de Paris) ; dernier scrutin public : {fdate(LAST_VOTE)}.</p></footer>
<script src="/static/hemi.js?v={JS_V}" defer></script>
</body></html>'''

def sidebar(current=None, counts=None):
    CUR = ' aria-current="page"'
    items = [f'<a class="subj" href="/"{CUR if current=="all" else ""}><span>Tous les votes</span><small>{len(S)}</small></a>',
             f'<a class="subj" href="/cette-semaine/"><span>Cette semaine</span><small>7 j</small></a>',
             f'<a class="subj" href="/budget/"><span>Les budgets</span><small></small></a>',
             f'<a class="subj" href="/comparer/"><span>Comparer 2 groupes</span><small></small></a>',
             f'<a class="subj" href="/mon-depute/"><span>Mon député</span><small></small></a>',
             f'<a class="subj" href="/essentiels/"{CUR if current=="essentiels" else ""}><span>L\'essentiel</span><small>{sum(1 for s in S if s["k"] in ("e","m"))}</small></a>']
    for t, l in THEME_LABEL.items():
        items.append(f'<a class="subj" href="/sujet/{t}/"{CUR if current==t else ""}><span>{l}</span><small>{counts.get(t,0) if counts else ""}</small></a>')
    return f'<aside class="side"><p class="eyebrow">Sujets</p><div class="subjects">{"".join(items)}</div></aside>'

THEME_COUNTS = {}
for s in S:
    for t in s["th"]: THEME_COUNTS[t] = THEME_COUNTS.get(t, 0) + 1

def paginate(items, base, page, per=PER_PAGE):
    n = max(1, math.ceil(len(items) / per)); page = max(1, min(page, n))
    chunk = items[(page-1)*per: page*per]
    prev = f'<a href="{base if page==2 else base+"page/"+str(page-1)+"/"}">← Plus récents</a>' if page > 1 else "<span></span>"
    nxt = f'<a href="{base}page/{page+1}/">Plus anciens →</a>' if page < n else "<span></span>"
    return chunk, f'<nav class="pager">{prev}<span style="color:var(--muted)">page {page} / {n}</span>{nxt}</nav>', n

# ----------------------------------------------------------------------------- pages
def page_list(items, base, current, lede, desc, title, page=1, nav=None):
    chunk, pager, n = paginate(items, base, page)
    body = f'''<div class="grid">{sidebar(current, THEME_COUNTS)}<main class="main">
<p class="lede">{lede}</p><p class="dek">{esc(desc)}</p>
<div class="list">{"".join(entry(s) for s in chunk)}</div>{pager}</main></div>'''
    path = base if page == 1 else f"{base}page/{page}/"
    write(path, layout(title if page == 1 else f"{title} · page {page}", body, desc=desc, path=path, current=nav or ("votes" if current=="all" else "sujets")))
    return n

def build_essentiels():
    """Sélection mécanique, sans choix humain : votes sur l'ensemble d'un texte + motions de censure."""
    allv = sorted([s for s in S if s["k"] in ("e", "m")], key=lambda s: (s["d"], s["n"]), reverse=True)
    motions = [s for s in allv if s["k"] == "m" and "censure" in s["ti"].lower()]
    rejets = [s for s in allv if s["k"] == "m" and "censure" not in s["ti"].lower()]
    finals = [s for s in allv if s["k"] == "e"]
    rule = ('<p class="hint" style="margin:-6px 0 18px">Règle de sélection, sans choix humain : tous les votes sur l\'ensemble d\'un texte (adoption ou rejet d\'une loi), '
            'toutes les motions de rejet préalable (qui enterrent un texte sans débat) et toutes les motions de censure. Aucun amendement, aucun tri par importance. <a href="/methode/">Méthode</a> · '
            f'<a href="/essentiels/motions-de-censure/">Motions de censure seules ({len(motions)})</a> · Par groupe : ' + " ".join(f'<a href="/groupe/{x.lower()}/essentiels/">{x}</a>' for x in ORDER) + '</p>')
    lede = f"<b>L'essentiel.</b> Les {len(allv)} votes qui décident du sort d'une loi ou d'un gouvernement : {len(finals)} votes sur l'ensemble d'un texte, {len(rejets)} motions de rejet préalable et {len(motions)} motions de censure."
    desc = "Les votes décisifs de l'Assemblée nationale : adoption ou rejet de chaque loi, motions de censure. Ce que chaque groupe (RN, LFI, EPR, PS, LR…) a voté, sans sélection éditoriale."
    title = f"L'essentiel : les votes décisifs de l'Assemblée · {NAME}"
    n = page_list(allv, "/essentiels/", "essentiels", lede + rule, desc, title, nav="essentiels")
    for p in range(2, n+1): page_list(allv, "/essentiels/", "essentiels", lede + rule, desc, title, p, nav="essentiels")
    lede_m = f"<b>Motions de censure.</b> Les {len(motions)} motions déposées depuis octobre 2024, et le vote de chaque groupe. Une motion est adoptée si 289 députés au moins la votent."
    desc_m = "Toutes les motions de censure de la 17e législature : qui a voté pour renverser le gouvernement, groupe par groupe et député par député."
    title_m = f"Motions de censure : qui a voté pour ? · {NAME}"
    n = page_list(motions, "/essentiels/motions-de-censure/", "essentiels", lede_m, desc_m, title_m, nav="essentiels")
    for p in range(2, n+1): page_list(motions, "/essentiels/motions-de-censure/", "essentiels", lede_m, desc_m, title_m, p, nav="essentiels")
    for gid in ORDER: build_group_essentiels(gid, allv)
    return n

def build_group_essentiels(gid, allv):
    """Le groupe face aux votes décisifs (même règle fixe que /essentiels/)."""
    votes = [s for s in allv if gid in s["gm"]]
    if not votes: return
    c = {"pour": 0, "contre": 0, "abstention": 0, "absent": 0}
    for s in votes: c[group_pos(s["gm"][gid])] += 1
    name = GN[gid]; col = COL[gid]
    lede = f"<b>{esc(name)}</b> face aux <b>{len(votes)} votes décisifs</b> de la législature (ensemble d'un texte, motions de rejet, motions de censure). En position majoritaire : pour {c['pour']} fois, contre {c['contre']} fois, abstention {c['abstention']} fois, absent {c['absent']} fois."
    rows = []
    for s in votes:
        g = s["gm"][gid]; p = group_pos(g); ok = s["s"] == 1
        st = {"pour": f"background:{col};color:#fff", "contre": f"background:repeating-linear-gradient(-45deg,{col} 0 2px,#fff 2px 4px);color:#000", "abstention": f"background:repeating-linear-gradient(45deg,{col} 0 2px,#fff 2px 5px);color:#000", "absent": f"background:#fff;box-shadow:inset 0 0 0 1px {col};color:#000"}[p]
        rows.append(f'<article class="entry"><div class="cat"><span><b>{THEME_LABEL[s["th"][0]]}</b> · {KIND.get(s["k"],"Vote")} · <time datetime="{s["d"]}">{fdate(s["d"])}</time></span><span>Scrutin nº {s["n"]}</span></div>'
                    f'<h3><a href="{s["url"]}">{esc(title_of(s))}</a></h3>'
                    f'<div class="result"><span class="pill" style="{st}">{gid} : {p}</span><span class="tally"><b>{g["pour"]}</b> pour · <b>{g["contre"]}</b> contre · <b>{g["abstention"]}</b> abst. · {g["absent"]+g["nonVotant"]} absents sur {g["membres"]}</span>'
                    f'<span class="pill {"ok" if ok else "no"}" style="margin-left:auto">{"Adopté" if ok else "Rejeté"}</span></div>{mini_bar(s)}</article>')
    body = f'''<div class="grid">{sidebar("essentiels", THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/groupes/">Groupes</a> › <a href="/groupe/{gid.lower()}/">{esc(name)}</a> › L'essentiel</p>
<p class="lede">{lede}</p>
<div class="stat-row"><div class="stat"><b>{c['pour']}</b><span>votes pour</span></div><div class="stat"><b>{c['contre']}</b><span>votes contre</span></div><div class="stat"><b>{c['abstention']}</b><span>abstentions</span></div><div class="stat"><b>{c['absent']}</b><span>absents en majorité</span></div></div>
<p class="hint">Même règle fixe que la page <a href="/essentiels/">L'essentiel</a>, sans sélection éditoriale. La pastille indique la position majoritaire du groupe ; le résultat du vote est à droite. Autres groupes : {" · ".join(f'<a href="/groupe/{x.lower()}/essentiels/">{x}</a>' for x in ORDER if x != gid)}.</p>
<div class="share"><button type="button" data-share>Partager</button><a href="/og/groupe-{gid.lower()}-carre.png" download>Image carrée</a><a href="/og/groupe-{gid.lower()}-story.png" download>Image story</a></div>
<div class="list">{"".join(rows)}</div></main></div>'''
    path = f"/groupe/{gid.lower()}/essentiels/"
    write(path, layout(f"{name} : ses votes sur l'essentiel · {NAME}", body, desc=re.sub(r"<[^>]+>", "", lede), path=path, current="essentiels", og_image=f"{SITE}/og/groupe-{gid.lower()}.png"))

def build_lists():
    allv = sorted(S, key=lambda s: (s["d"], s["n"]), reverse=True)
    n = page_list(allv, "/", "all", f"<b>Tous les votes.</b> Les {len(S):,} scrutins publics de la législature, du plus récent au plus ancien.".replace(",", " "),
                  "Chaque scrutin public de l'Assemblée nationale, avec le vote de chaque groupe et de chaque député. Sans avis, sans note.", f"{NAME} — Tous les votes de l'Assemblée nationale")
    for p in range(2, n+1): page_list(allv, "/", "all", "<b>Tous les votes.</b>", "Scrutins publics de l'Assemblée nationale, du plus récent au plus ancien.", f"{NAME} — Tous les votes", p)
    for t, l in THEME_LABEL.items():
        items = [s for s in allv if t in s["th"]]
        lede = f"<b>{l}.</b> {len(items)} votes de l'Assemblée nationale sur ce sujet, d'octobre 2024 à {MONTHS[int(LAST_VOTE[5:7])-1]} {LAST_VOTE[:4]}."
        desc = f"{l} : ce que chaque groupe politique (RN, LFI, EPR, PS, LR…) a réellement voté à l'Assemblée nationale. {len(items)} scrutins, votes par député."
        n = page_list(items, f"/sujet/{t}/", t, lede, desc, f"{l} : qui a voté quoi à l'Assemblée ? · {NAME}")
        for p in range(2, n+1): page_list(items, f"/sujet/{t}/", t, lede, desc, f"{l} : qui a voté quoi à l'Assemblée ? · {NAME}", p)
        # groupe × sujet
        for gid in ORDER:
            build_group_theme(gid, t, items)
    # index sujets
    body = f'<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Par sujet.</b> Seize sujets, choisis pour couvrir tout le spectre du débat public.</p><ul class="tx-list">' + \
        "".join(f'<li><a href="/sujet/{t}/"><b>{l}</b></a> · {THEME_COUNTS.get(t,0)} votes</li>' for t, l in THEME_LABEL.items()) + "</ul></main></div>"
    write("/sujets/", layout(f"Les votes par sujet · {NAME}", body, desc="Les votes de l'Assemblée nationale classés en seize sujets.", path="/sujets/", current="sujets"))

def build_votes():
    for s in S:
        t = title_of(s); ok = s["s"] == 1
        q = f"Qui a voté {'pour' if ok else 'contre'} ? {t}" if s["k"] != "a" else f"{t} : qui a voté quoi ?"
        desc = re.sub(r"<[^>]+>", "", sentence(s))[:300]
        a = s.get("a")
        why = ""
        if a and a["ex"]:
            gr = f" ({a['gr']})" if a["gr"] else ""
            why = "<div class=\"qa\"><h2>Ce que l'auteur de l'amendement explique</h2><p>« " + esc(a["ex"]) + " »</p><p class=\"hint\" style=\"margin-top:6px\">Exposé sommaire déposé par " + esc(a["au"]) + gr + ". C'est son argument, cité tel quel.</p>" + \
                  ("<h2 style=\"margin-top:14px\">Texte de l'amendement</h2><p class=\"disp\" style=\"display:block;background:var(--panel);padding:10px 12px;font-family:var(--sans);font-size:14px\">" + esc(a["di"]) + "</p>" if a["di"] else "") + "</div>"
        jsonld = {"@context": "https://schema.org", "@type": "Article", "headline": q, "datePublished": s["d"], "dateModified": BUILD_DATE,
                  "inLanguage": "fr", "isBasedOn": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{s['n']}", "publisher": {"@type": "Organization", "name": NAME, "url": SITE},
                  "about": [THEME_LABEL[x] for x in s["th"]], "description": desc}
        body = f'''<div class="grid">{sidebar(s['th'][0], THEME_COUNTS)}<main class="main">
<p class="crumbs"><a href="/">Tous les votes</a> › <a href="/sujet/{s['th'][0]}/">{THEME_LABEL[s['th'][0]]}</a> › Scrutin nº {s['n']}</p>
<article class="entry" style="border:0">
  <div class="cat"><span>{KIND.get(s['k'],'Vote')} · <time datetime="{s['d']}">{fdate(s['d'])}</time> · <a href="/texte/{s['tx']}-{slug(TX[s['tx']],50)}/">{esc(TX[s['tx']][:90])}</a></span><span>Scrutin nº {s['n']}</span></div>
  <h1 style="font-family:var(--serif);font-size:clamp(26px,3.4vw,36px);line-height:1.15;font-weight:400;margin:8px 0 0;max-width:30ch;text-wrap:balance">{esc(t)}</h1>
  {f'<p class="off">{esc(clean_title(s["ti"]))}</p>' if s['k'] in ("a", "m") else ""}
  <div class="result"><span class="pill {'ok' if ok else 'no'}">{'Adopté' if ok else 'Rejeté'}</span><span class="tally"><b>{s['t'][0]}</b> pour · <b>{s['t'][1]}</b> contre · <b>{s['t'][2]}</b> abst.</span><span>{s['v']} votants sur 577</span></div>
  <p class="summary-text">{sentence(s)}</p>
  <div class="share"><button type="button" data-share>Partager</button>{f'<a href="/og/{s["n"]}-carre.png" download>Image carrée</a>' if has_card(s) else ""}{f'<a href="/og/{s["n"]}-story.png" download>Image story</a>' if s["k"] in ("e", "m") else ""}<a href="https://www.assemblee-nationale.fr/dyn/17/scrutins/{s['n']}" rel="noopener" target="_blank">Scrutin officiel ↗</a></div>
  <div class="hlegend" style="margin-top:18px"><span>● Pour</span><span>⊗ Contre</span><span>▨ Abstention</span><span>○ Absent ou non-votant</span><span>· couleur = groupe</span><label class="toggle" style="margin-left:auto"><input type="checkbox" id="cvd"> Couleurs adaptées</label></div>
  <div class="hemi-wrap" data-vote="{s['vote']}" data-date="{s['d']}"><noscript>Activez JavaScript pour l'hémicycle interactif ; le détail par député est dans le tableau ci-dessous.</noscript></div>
  {group_table(s)}
  {why}
  <h2 class="sec">Le vote de chaque député</h2>
  <div id="deps"><p class="hint">Chargement du tableau nominatif…</p></div>
</article></main></div>'''
        write(s["url"], layout(f"{q} · {NAME}", body, desc=desc, path=s["url"], jsonld=jsonld, og_image=f"{SITE}/og/{s['n']}.png" if has_card(s) else None, current="votes"))

def build_group_theme(gid, t, items):
    votes = [s for s in items if gid in s["gm"]]
    if not votes: return
    c = {"pour": 0, "contre": 0, "abstention": 0, "absent": 0}
    for s in votes: c[group_pos(s["gm"][gid])] += 1
    l = THEME_LABEL[t]; name = GN[gid]
    lede = f"<b>{name}</b> sur <b>{l.lower()}</b> : {len(votes)} votes. En position majoritaire : pour {c['pour']} fois, contre {c['contre']} fois, abstention {c['abstention']} fois, absent {c['absent']} fois."
    rows = "".join(f'<li><a href="{s["url"]}">{esc(title_of(s))}</a> <span style="color:var(--muted)">· {fdate(s["d"])} · {gid} : <b>{group_pos(s["gm"][gid])}</b> ({s["gm"][gid]["pour"]}/{s["gm"][gid]["contre"]}/{s["gm"][gid]["abstention"]})</span></li>' for s in votes[:200])
    body = f'''<div class="grid">{sidebar(t, THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/groupes/">Groupes</a> › <a href="/groupe/{gid.lower()}/">{esc(name)}</a> › {l}</p>
<p class="lede">{lede}</p>
<div class="stat-row"><div class="stat"><b>{c['pour']}</b><span>votes pour</span></div><div class="stat"><b>{c['contre']}</b><span>votes contre</span></div><div class="stat"><b>{c['abstention']}</b><span>abstentions</span></div><div class="stat"><b>{c['absent']}</b><span>absents en majorité</span></div></div>
<p class="hint">Position majoritaire du groupe à chaque scrutin ; entre parenthèses pour / contre / abstention. {"Les 200 votes les plus récents." if len(votes)>200 else ""}</p>
<ul class="tx-list">{rows}</ul></main></div>'''
    path = f"/groupe/{gid.lower()}/{t}/"
    write(path, layout(f"Que vote {name} sur {l.lower()} ? · {NAME}", body, desc=re.sub(r"<[^>]+>","",lede), path=path, current="groupes"))

def build_groups():
    items = []
    for gid in ORDER:
        g = GROUPS[gid]; votes = [s for s in S if gid in s["gm"]]
        part = sum(s["gm"][gid]["pour"]+s["gm"][gid]["contre"]+s["gm"][gid]["abstention"] for s in votes) / max(1, sum(s["gm"][gid]["membres"] for s in votes))
        per_theme = []
        for t, l in THEME_LABEL.items():
            tv = [s for s in votes if t in s["th"]]
            if not tv: continue
            c = {"pour": 0, "contre": 0, "abstention": 0, "absent": 0}
            for s in tv: c[group_pos(s["gm"][gid])] += 1
            per_theme.append(f'<li><a href="/groupe/{gid.lower()}/{t}/"><b>{l}</b></a> · {len(tv)} votes · pour {c["pour"]}, contre {c["contre"]}, abstention {c["abstention"]}, absent {c["absent"]}</li>')
        recent = sorted(votes, key=lambda s: s["d"], reverse=True)[:20]
        body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/groupes/">Groupes</a> › {gid}</p>
<p class="lede"><span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:{COL[gid]};vertical-align:middle;margin-right:8px"></span><b>{esc(g['nom'])}</b> ({gid}). {votes[-1]['gm'][gid]['membres'] if votes else ''} membres. Présence moyenne aux scrutins publics : <b>{round(100*part)} %</b>.</p>
<p><a href="/groupe/{gid.lower()}/essentiels/"><b>→ {esc(g['nom'])} sur l'essentiel</b></a> : les votes décisifs (lois entières, motions), sans sélection.</p>
<h2 class="sec">Par sujet</h2><ul class="tx-list">{"".join(per_theme)}</ul>
<h2 class="sec">Derniers votes</h2><div class="list">{"".join(entry(s) for s in recent)}</div></main></div>'''
        path = f"/groupe/{gid.lower()}/"
        write(path, layout(f"Que vote {g['nom']} ? · {NAME}", body, desc=f"Tous les votes du groupe {g['nom']} ({gid}) à l'Assemblée nationale, sujet par sujet, avec la présence.", path=path, current="groupes"))
        items.append(f'<li><a href="{path}"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{COL[gid]};margin-right:8px"></span><b>{gid}</b> — {esc(g["nom"])}</a> · présence {round(100*part)} %</li>')
    body = f'<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Par groupe.</b> Les douze groupes de l\'Assemblée, dans l\'ordre de l\'hémicycle, de gauche à droite.</p><ul class="tx-list">{"".join(items)}</ul></main></div>'
    write("/groupes/", layout(f"Les votes par groupe politique · {NAME}", body, desc="Ce que vote chaque groupe politique de l'Assemblée nationale.", path="/groupes/", current="groupes"))

def build_textes():
    for i, t in enumerate(TX):
        votes = sorted([s for s in S if s["tx"] == i], key=lambda s: (s["d"], s["n"]))
        finals = [s for s in votes if s["k"] in ("e", "m")]
        FINALS = ("<h2 class=\"sec\">Votes sur l'ensemble du texte et motions</h2><div class=\"list\">" + "".join(entry(x) for x in finals) + "</div>") if finals else ""
        body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/">Tous les votes</a> › Texte</p>
<p class="lede"><b>{esc(t)}</b>. {len(votes)} scrutins publics, du {fdate(votes[0]['d'])} au {fdate(votes[-1]['d'])}.</p>
{FINALS}
<h2 class="sec">Tous les scrutins sur ce texte</h2><ul class="tx-list">{"".join(f'<li><a href="{s["url"]}">{esc(title_of(s))}</a> <span style="color:var(--muted)">· {fdate(s["d"])} · {"adopté" if s["s"] else "rejeté"} {s["t"][0]}/{s["t"][1]}</span></li>' for s in votes)}</ul></main></div>'''
        path = f"/texte/{i}-{slug(t,50)}/"
        write(path, layout(f"{t[:80]} : les votes · {NAME}", body, desc=f"Tous les votes de l'Assemblée nationale sur : {t}.", path=path, current="votes"))

def group_at(d, date):
    g = d["g"][0][1]
    for dd, gi in d["g"]:
        if dd <= date: g = gi
    return ORDER[g]

def deputy_stats(i, d):
    """Chiffres bruts d'un député : présence, votes, essentiel, écarts avec la majorité de son groupe."""
    LBL = {"P": "pour", "C": "contre", "A": "abstention", "N": "non-votant"}
    my = []; cnt = {"P": 0, "C": 0, "A": 0, "N": 0}; present = 0; eligible = 0
    ess = {"pour": 0, "contre": 0, "abstention": 0, "absent": 0}; ecarts = []
    for s in S:
        v = s["vote"][i] if i < len(s["vote"]) else "."
        in_mandate = d["f"] <= s["d"] <= d["l"]
        if in_mandate: eligible += 1
        if v != ".": cnt[v] += 1; present += v in "PCA"
        if v != "." and s["k"] != "a": my.append((s, v))
        if s["k"] in ("e", "m") and in_mandate:
            ess[LBL[v] if v in "PCA" else "absent"] += 1
        if v in "PCA":
            gid = group_at(d, s["d"]); g = s["gm"].get(gid)
            if g and gid != "NI":
                gp = group_pos(g)
                if gp != "absent" and gp != LBL[v]: ecarts.append((s, v, gp))
    my.sort(key=lambda x: x[0]["d"], reverse=True)
    ecarts.sort(key=lambda x: (x[0]["k"] not in ("e", "m"), -int(x[0]["d"].replace("-", ""))))
    n_ess = sum(ess.values())
    return {"my": my, "cnt": cnt, "present": present, "eligible": eligible, "rate": round(100 * present / max(1, eligible)),
            "ess": ess, "ess_rate": round(100 * (n_ess - ess["absent"]) / max(1, n_ess)), "ecarts": ecarts, "LBL": LBL}

def compute_medians():
    """Médianes de présence sur tous les députés ayant plus de 100 scrutins de mandat (repère, pas jugement)."""
    import statistics
    r, e = [], []
    for i, d in enumerate(DEPS):
        st = deputy_stats(i, d)
        if st["eligible"] > 100: r.append(st["rate"]); e.append(st["ess_rate"])
    return round(statistics.median(r)), round(statistics.median(e))

def build_deputes():
    rows_index = []
    MED, MED_ESS = compute_medians()
    write("/api/medianes.json", json.dumps({"presence": MED, "presence_essentiel": MED_ESS}))
    for i, d in enumerate(DEPS):
        st = deputy_stats(i, d); LBL = st["LBL"]; cnt = st["cnt"]; rate = st["rate"]; ess = st["ess"]; ecarts = st["ecarts"]
        gid = ORDER[d["g"][-1][1]]
        n_ess = sum(ess.values()); n_part = cnt["P"] + cnt["C"] + cnt["A"]
        POS = {"P": ("pour", "background:%s;color:#fff"), "C": ("contre", "background:repeating-linear-gradient(-45deg,%s 0 2px,#fff 2px 4px);color:#000;text-shadow:0 0 4px #fff,0 0 4px #fff"), "A": ("abstention", "background:repeating-linear-gradient(45deg,%s 0 2px,#fff 2px 5px);color:#000;text-shadow:0 0 4px #fff,0 0 4px #fff"), "N": ("non-votant", "background:#fff;box-shadow:inset 0 0 0 1px %s;color:#000")}
        col = COL[gid]
        def vote_card(s, v):
            lab, st = POS[v]; ok = s["s"] == 1
            sw = st.split(";")[0].replace("%s", col) if v != "N" else f"background:#fff;box-shadow:inset 0 0 0 1.5px {col}"
            return (f'<article class="vc" data-v="{v}"><div class="cat"><span><b>{THEME_LABEL[s["th"][0]]}</b> · {KIND.get(s["k"], "Vote")} · <time datetime="{s["d"]}">{fdate(s["d"])}</time></span><span>nº {s["n"]}</span></div>'
                    f'<h3><a href="{s["url"]}">{esc(title_of(s))}</a></h3>'
                    f'<div class="result"><span class="pill vpos" style="border-color:{col}"><i style="{sw}"></i>{lab}</span><span class="pill {"ok" if ok else "no"}">{"Adopté" if ok else "Rejeté"}</span><span class="tally">{s["t"][0]} pour · {s["t"][1]} contre · {s["t"][2]} abst.</span></div></article>')
        cards = "".join(vote_card(s, v) for s, v in st["my"])
        nv = len(st["my"]); npos = {k: sum(1 for _, v in st["my"] if v == k) for k in "PCAN"}
        ec_rows = "".join(f'<li><a href="{s["url"]}">{esc(title_of(s))}</a> <span style="color:var(--muted)">· {fdate(s["d"])} · a voté <b>{LBL[v]}</b>, son groupe {gp}</span></li>' for s, v, gp in ecarts[:40])
        pe = (f"{100*len(ecarts)/max(1,n_part):.1f}".replace(".", ",") if 100*len(ecarts)/max(1,n_part) < 1 else str(round(100*len(ecarts)/max(1,n_part))))
        MORE40 = "Les 40 plus significatifs (textes entiers et motions d'abord)."
        ECARTS = (f'<details class="fold"><summary><b>Ses écarts avec son groupe</b> <span class="muted">· {len(ecarts)} scrutins ({pe} % de ses votes)</span></summary><p class="hint">Les scrutins où {esc(d["nom"])} a voté autrement que la majorité de son groupe. Fait brut, sans interprétation : un écart peut être un désaccord comme une consigne de vote. {MORE40 if len(ecarts) > 40 else ""}</p><ul class="tx-list">{ec_rows}</ul></details>') if ecarts else ""
        bar = lambda pct, med: f'<div class="gauge"><i style="width:{pct}%;background:{col}"></i><b style="left:{med}%" title="médiane des députés : {med} %"></b></div>'
        essbar = '<div class="bar" style="border-color:#000">' + "".join(f'<i style="width:{100*ess[k]/max(1,n_ess):.1f}%;{POS[c][1].split(";")[0].replace("%s", col)}"></i>' for k, c in (("pour","P"),("contre","C"),("abstention","A"),("absent","N"))) + "</div>"
        mandat = f"{fdate(d['f'])} → {'en cours' if d['l'] >= LAST_VOTE else fdate(d['l'])}"
        share = f'<div class="share"><button type="button" data-share>Partager</button><a href="/og/depute-{d["id"]}-carre.png" download>Image carrée</a><a href="/groupe/{gid.lower()}/">Son groupe</a></div>'
        FILTERS = "".join(f'<button type="button" class="chipbtn" data-f="{k}">{l} <small>{nv if k == "*" else npos[k]}</small></button>' for k, l in (("*", "Tous"), ("P", "Pour"), ("C", "Contre"), ("A", "Abstention")))
        JS = "(function(){var L=[].slice.call(document.querySelectorAll('.vc')),N=20,f='*',shown=N,more=document.getElementById('more'),btns=document.querySelectorAll('.chipbtn');function draw(){var k=0;L.forEach(function(c){var ok=(f=='*'||c.dataset.v==f);c.hidden=!(ok&&k<shown);if(ok)k++;});more.hidden=k<=shown;more.textContent='Voir plus ('+(k-shown)+' autres)';}btns.forEach(function(b){b.addEventListener('click',function(){f=b.dataset.f;shown=N;btns.forEach(function(x){x.classList.toggle('on',x===b);});draw();});});more.addEventListener('click',function(){shown+=N;draw();});btns[0].classList.add('on');draw();})();"
        body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/deputes/">Députés</a> › {esc(d['nom'])}</p>
<header class="dep-head">{photo_tag(d, 120)}<div><h1 class="dep-name">{esc(d['nom'])}</h1>
<p class="dep-meta">{(esc(d['dept'])+(" · "+d['circo']+"ᵉ circonscription" if d['circo'] else "")+" · ") if d['dept'] else ""}<a class="gchip" href="/groupe/{gid.lower()}/" style="--c:{col}">{gid} · {esc(GN[gid])}</a></p>
<p class="dep-meta muted">Mandat : {mandat} · {st['eligible']} scrutins publics pendant son mandat</p>{share}</div></header>
<section class="kpis">
<div class="kpi"><b>{rate} %</b><span>présence, tous scrutins</span>{bar(rate, MED)}<small>médiane des députés : {MED} %</small></div>
<div class="kpi"><b>{st['ess_rate']} %</b><span>présence, votes décisifs</span>{bar(st['ess_rate'], MED_ESS)}<small>médiane : {MED_ESS} %</small></div>
<div class="kpi"><b>{len(ecarts)}</b><span>écarts avec son groupe</span><small>{pe} % de ses {n_part} votes</small></div>
<div class="kpi"><b>{cnt['P']} <em>/</em> {cnt['C']} <em>/</em> {cnt['A']}</b><span>pour / contre / abstention</span><small>tous scrutins confondus</small></div>
</section>
<p class="hint">Présence = a pris part au vote. « Tous scrutins » compte aussi les milliers de votes d'amendements en séance de nuit, d'où des taux bas pour tout le monde ; « votes décisifs » = lois entières et motions. La médiane est un repère, pas une norme. <a href="/methode/">Méthode</a>.</p>
<h2 class="sec">Sur l'essentiel <span class="muted">· {n_ess} votes décisifs pendant son mandat</span></h2>
{essbar}
<div class="legend-row"><span><i style="background:{col}"></i> pour {ess['pour']}</span><span><i style="{POS['C'][1].split(';')[0].replace('%s', col)}"></i> contre {ess['contre']}</span><span><i style="{POS['A'][1].split(';')[0].replace('%s', col)}"></i> abstention {ess['abstention']}</span><span><i style="background:#fff;box-shadow:inset 0 0 0 1px {col}"></i> absent {ess['absent']}</span></div>
{ECARTS}
<h2 class="sec">Ses votes <span class="muted">· {nv} textes entiers, articles et motions</span></h2>
<div class="chips">{FILTERS}</div>
<div class="list vlist">{cards}</div>
<button type="button" id="more" class="more" hidden>Voir plus</button>
<p class="hint">Les votes sur amendements sont consultables scrutin par scrutin, et dans la <a href="/recherche/">recherche</a>.</p>
<script>{JS}</script></main></div>'''
        jsonld = {"@context": "https://schema.org", "@type": "Person", "name": d["nom"], "jobTitle": "Député·e", **({"image": f"{SITE}/photos/{d['id']}.jpg"} if has_photo(d) else {}), "memberOf": {"@type": "Organization", "name": GN[gid]}, "url": SITE + d["url"]}
        desc = f"Les votes de {d['nom']} ({gid}) à l'Assemblée nationale : présence {rate} % (médiane {MED} %), {st['ess_rate']} % sur les votes décisifs, {cnt['P']} pour, {cnt['C']} contre, {cnt['A']} abstentions. Sur les votes décisifs : {ess['pour']} pour, {ess['contre']} contre. {len(ecarts)} écarts avec son groupe."
        write(d["url"], layout(f"{d['nom']} : ses votes à l'Assemblée · {NAME}", body, desc=desc, path=d["url"], jsonld=jsonld, current="deputes", og_image=f"{SITE}/og/depute-{d['id']}.png"))
        rows_index.append((d["famille"] or d["nom"], f'<li class="dep-row">{photo_tag(d, 32)}<span><a href="{d["url"]}">{esc(d["nom"])}</a> <span style="color:var(--muted)">· {gid}{(" · "+esc(d["dept"])) if d["dept"] else ""} · présence {rate} % · décisifs {st["ess_rate"]} %</span></span></li>'))
    rows_index.sort(key=lambda x: norm(x[0]))
    ONINPUT = "const q=this.value.toLowerCase();document.querySelectorAll('.tx-list li').forEach(l=>l.hidden=!l.textContent.toLowerCase().includes(q))"
    body = f'<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Par député.</b> {len(DEPS)} députés ayant siégé pendant la législature.</p><input class="search" type="search" placeholder="Nom, département, groupe" oninput="{esc(ONINPUT)}"><ul class="tx-list">{"".join(r for _, r in rows_index)}</ul></main></div>'
    write("/deputes/", layout(f"Les votes par député · {NAME}", body, desc="Retrouvez votre député et ce qu'il ou elle a voté.", path="/deputes/", current="deputes"))
    write("/api/deputes.json", json.dumps([{"id": d["id"], "nom": d["nom"], "dept": d["dept"], "circo": d["circo"], "g": d["g"], "f": d["f"], "l": d["l"], "slug": d["slug"]} for d in DEPS], ensure_ascii=False, separators=(",", ":")))

def build_methode():
    body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Méthode.</b> Comment ce site est fabriqué, et ce qu'il ne fait pas.</p>
<div class="qa"><h2>D'où viennent les chiffres</h2><p>De l'open data de l'Assemblée nationale : scrutins, amendements, dossiers législatifs et liste des députés de la 17ᵉ législature. Le site est régénéré chaque nuit. Chaque page de vote renvoie au scrutin officiel. Les groupes sont affichés dans l'ordre de l'hémicycle, de gauche à droite, avec les couleurs que l'Assemblée publie elle-même. « Absent » = membres du groupe moins votants et non-votants déclarés. Les photos des députés sont les portraits officiels publiés par l'Assemblée nationale.</p></div>
<div class="qa"><h2>La présence</h2><p>Présence = le député a pris part au vote (pour, contre ou abstention) sur les scrutins publics tenus pendant son mandat. Tous scrutins confondus, les taux sont bas pour tout le monde (médiane autour de 23 %), parce que des milliers de votes portent sur des amendements en séance de nuit devant quelques dizaines de députés. Le taux sur les votes décisifs (lois entières, motions) est plus parlant. La médiane des députés est affichée comme repère, pas comme norme.</p></div>
<div class="qa"><h2>« L'essentiel »</h2><p>Cette page n'est pas un choix éditorial. Elle applique une règle fixe : tous les votes sur l'ensemble d'un texte (le moment où une loi est adoptée ou rejetée), toutes les motions de rejet préalable et toutes les motions de censure. Rien d'autre, rien de moins. Les amendements, même très commentés, restent dans « Tous les votes » et dans les pages par sujet.</p></div>
<div class="qa"><h2>Comment les votes sont rangés par sujet</h2><p>Chaque vote est rattaché à son texte de loi ; chaque texte est classé dans un à trois sujets (liste publique, corrigeable). Pour les budgets, qui touchent à tout, chaque amendement est classé d'après son contenu par mots-clés. Le classement est automatique ; les erreurs peuvent être signalées et sont corrigées dans le fichier public de classement.</p></div>
<div class="qa"><h2>« L'auteur explique »</h2><p>Pour un amendement, la phrase affichée est l'exposé sommaire écrit par le député qui l'a déposé. C'est son argument, pas une description neutre : il est cité comme tel, avec son nom et son groupe.</p></div>
<div class="qa"><h2>L'hémicycle</h2><p>Un point par député, couleur du groupe, texture du vote : plein = pour, croix = contre, hachures = abstention, vide = absent ou non-votant. Les députés sont placés par groupe, de gauche à droite ; la place d'un point n'est pas le siège réel. Le bouton « couleurs adaptées » remplace la palette officielle par une palette lisible pour les daltoniens.</p></div>
<div class="qa"><h2>Ce que le site ne fait pas</h2><p>Il ne dit pas si un vote est une avancée ou un recul. Il ne choisit pas les sujets selon un programme. Il ne résume pas les textes à la place de leurs auteurs. Il n'a pas de compte à rendre à un parti, un média ou un financeur.</p></div>
</main></div>'''
    write("/methode/", layout(f"Méthode · {NAME}", body, desc="Comment ilsvotentquoi.fr est fabriqué : sources, classement par sujet, neutralité.", path="/methode/", current="methode"))

def build_recherche():
    """Index compact pour la recherche côté client + page de recherche."""
    idx = []
    for s in sorted(S, key=lambda s: (0 if s["k"] in ("e", "m") else 1, -int(s["d"].replace("-", "")), -s["n"])):
        a = s.get("a") or {}
        idx.append([s["n"], s["d"], s["s"], s["k"], title_of(s)[:110], "" if s["k"] == "a" else TX[s["tx"]][:90], (a.get("au") or "")[:40], s["th"][0], s["url"].split("/")[2], s["t"][0], s["t"][1]])
    write("/api/index.json", json.dumps(idx, ensure_ascii=False, separators=(",", ":")))
    JS = """
(function(){var q=document.getElementById('q'),out=document.getElementById('out'),cnt=document.getElementById('cnt'),I=null;
var TH=window.IVQ.themes,K={a:'Amendement',e:'Texte entier',m:'Motion',r:'Article',u:'Vote'};
function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');}
function fd(d){var m=['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];return parseInt(d.slice(8))+' '+m[parseInt(d.slice(5,7))-1]+' '+d.slice(0,4);}
function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function run(){var v=norm(q.value.trim());if(!I){out.innerHTML='<p class="hint">Chargement de l\\'index…</p>';return;}
 if(v.length<2){out.innerHTML='';cnt.textContent='';return;}
 var w=v.split(/\\s+/),r=[];
 for(var i=0;i<I.length&&r.length<300;i++){var s=I[i],h=s[12];var ok=true;for(var j=0;j<w.length;j++){if(h.indexOf(w[j])<0){ok=false;break;}}if(ok)r.push(s);}
 cnt.textContent=r.length?(r.length>=300?'300 premiers résultats':r.length+' résultat'+(r.length>1?'s':'')):'Aucun résultat';
 out.innerHTML=r.map(function(s){return '<li><a href="/vote/'+s[8]+'/">'+esc(s[4])+'</a> <span style="color:var(--muted)">· '+K[s[3]]+' · '+fd(s[1])+' · '+TH[s[7]]+' · <b>'+(s[2]?'adopté':'rejeté')+'</b> '+s[9]+'/'+s[10]+(s[6]?' · '+esc(s[6]):'')+'</span></li>';}).join('');}
fetch('/api/index.json').then(function(r){return r.json();}).then(function(d){I=d;for(var i=0;i<I.length;i++){var s=I[i];s[12]=norm(s[4]+' '+s[5]+' '+s[6]+' '+String(s[0])+' '+s[1]+' '+TH[s[7]]+' '+K[s[3]]);}run();});
q.addEventListener('input',run);var u=new URLSearchParams(location.search).get('q');if(u){q.value=u;}
document.getElementById('f').addEventListener('submit',function(e){e.preventDefault();history.replaceState(null,'','?q='+encodeURIComponent(q.value));run();});})();
"""
    body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Recherche.</b> Un mot, un nom de député, un numéro de scrutin, un sujet. Tous les {len(S)} votes, en direct.</p>
<form id="f" role="search"><input class="search" id="q" type="search" placeholder="aide à mourir, Panot, retraites, 8434…" autofocus autocomplete="off" style="max-width:100%;font-size:17px;padding:10px 14px"></form>
<p class="hint" id="cnt" style="margin-top:8px"></p><ul class="tx-list" id="out"></ul>
<script>{JS}</script></main></div>'''
    write("/recherche/", layout(f"Recherche · {NAME}", body, desc="Cherchez un vote de l'Assemblée nationale par mot-clé, député, sujet ou numéro de scrutin.", path="/recherche/", current="recherche", extra_head=f"<script>window.IVQ.themes={json.dumps(THEME_LABEL, ensure_ascii=False)}</script>"))

def build_statut():
    """Page et JSON de statut : le site tourne-t-il ? Les données bougent-elles ?"""
    last = max(S, key=lambda s: (s["d"], s["n"]))
    n7 = sum(1 for s in S if s["d"] >= (datetime.date.fromisoformat(BUILD_DATE) - datetime.timedelta(days=7)).isoformat())
    days = (datetime.date.fromisoformat(BUILD_DATE) - datetime.date.fromisoformat(LAST_VOTE)).days
    write("/api/statut.json", json.dumps({"genere_le": _now.isoformat(timespec="minutes"), "dernier_scrutin": LAST_VOTE, "numero_dernier_scrutin": last["n"],
                                          "scrutins": len(S), "deputes": len(DEPS), "textes": len(TX), "scrutins_7_jours": n7, "jours_depuis_dernier_vote": days}))
    body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Statut.</b> Le site se régénère chaque nuit à partir de l'open data de l'Assemblée. Voici où il en est.</p>
<div class="stat-row"><div class="stat"><b>{BUILD_STAMP.split(" à ")[1]}</b><span>dernière régénération, le {BUILD_STAMP.split(" à ")[0]}</span></div><div class="stat"><b>{fdate(LAST_VOTE)}</b><span>dernier scrutin public (nº {last["n"]})</span></div><div class="stat"><b>{n7}</b><span>scrutins ces 7 derniers jours</span></div><div class="stat"><b>{len(S):,}</b><span>scrutins au total</span></div></div>
<p class="hint">{"L'Assemblée n'a pas tenu de scrutin public depuis " + str(days) + " jours : vacances parlementaires ou semaine sans séance. Le site continue de se régénérer chaque nuit et affichera le prochain vote le lendemain matin." if days > 10 else "Le dernier vote date de moins de dix jours : le site suit l'actualité."}</p>
<div class="qa"><h2>Comment vérifier</h2><p>Le bandeau noir en haut de chaque page indique la date du dernier vote et l'heure de la dernière régénération. Le même statut est disponible en JSON : <a href="/api/statut.json">/api/statut.json</a>. Le code et l'historique des mises à jour sont publics sur <a href="https://github.com/YolandM/ilsvotentquoi" rel="noopener">GitHub</a>.</p></div>
</main></div>'''.replace(",", " ", 0)
    write("/statut/", layout(f"Statut du site · {NAME}", body.replace(f"{len(S):,}", f"{len(S):,}".replace(",", " ")), desc="Le site est-il à jour ? Date du dernier scrutin et de la dernière régénération.", path="/statut/", current=None))

def build_semaine():
    """Cette semaine à l'Assemblée : les scrutins des 7 derniers jours, décisifs d'abord."""
    since = (datetime.date.fromisoformat(BUILD_DATE) - datetime.timedelta(days=7)).isoformat()
    week = sorted([s for s in S if s["d"] >= since], key=lambda s: (0 if s["k"] in ("e", "m") else 1, -int(s["d"].replace("-", "")), -s["n"]))
    finals = [s for s in week if s["k"] in ("e", "m")]; amd = [s for s in week if s["k"] not in ("e", "m")]
    if week:
        lede = f"<b>Cette semaine à l'Assemblée.</b> {len(week)} scrutins publics depuis le {fdate(since)} : {len(finals)} votes décisifs (lois entières, motions) et {len(amd)} votes sur amendements ou articles."
        body_list = "".join(entry(s) for s in finals) + (f'<h2 class="sec">Amendements et articles</h2>' + "".join(entry(s) for s in amd[:60]) if amd else "")
    else:
        lede = f"<b>Cette semaine à l'Assemblée.</b> Aucun scrutin public depuis le {fdate(since)}. Dernier vote : le {fdate(LAST_VOTE)}."
        recent = sorted([s for s in S if s["k"] in ("e", "m")], key=lambda s: (s["d"], s["n"]), reverse=True)[:10]
        body_list = '<h2 class="sec">En attendant, les derniers votes décisifs</h2>' + "".join(entry(s) for s in recent)
    body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede">{lede}</p>
<p class="hint">Page régénérée chaque nuit. Les votes décisifs d'abord, puis les amendements. <a href="/statut/">Statut du site</a>.</p>
<div class="share"><button type="button" data-share>Partager cette semaine</button></div>
<div class="list">{body_list}</div></main></div>'''
    write("/cette-semaine/", layout(f"Cette semaine à l'Assemblée · {NAME}", body, desc="Les votes de l'Assemblée nationale des 7 derniers jours, groupe par groupe.", path="/cette-semaine/", current="votes"))

BUDGET_RX = re.compile(r"(loi de finances(?: rectificative| de fin de gestion)? pour (\d{4}))|(financement de la s[ée]curit[ée] sociale pour (\d{4}))", re.I)
def build_budgets():
    """Une page par budget (PLF + PLFSS d'une même année) : tous les scrutins, décisifs d'abord. Créée automatiquement dès le premier vote."""
    years = {}
    for i, tx in enumerate(TX):
        m = BUDGET_RX.search(tx)
        if m: years.setdefault(m.group(2) or m.group(4), []).append(i)
    out = []
    for y in sorted(years, reverse=True):
        idx = set(years[y]); votes = [s for s in S if s["tx"] in idx]
        finals = sorted([s for s in votes if s["k"] in ("e", "m")], key=lambda s: (s["d"], s["n"]), reverse=True)
        byt = collections.Counter(s["th"][0] for s in votes)
        lede = f"<b>Budget {y}.</b> {len(votes)} scrutins publics sur le projet de loi de finances et le financement de la sécurité sociale pour {y} : {len(finals)} votes décisifs, {len(votes)-len(finals)} amendements et articles."
        themes = "".join(f'<li><a href="/sujet/{k}/"><b>{THEME_LABEL[k]}</b></a> · {v} votes</li>' for k, v in byt.most_common())
        NOFINAL = "<p class=\"hint\">Pas encore de vote sur l'ensemble du texte.</p>"
        texts = "".join(f'<li><a href="/texte/{i}-{slug(TX[i],50)}/">{esc(TX[i])}</a></li>' for i in years[y])
        body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/budget/">Budgets</a> › {y}</p><p class="lede">{lede}</p>
<p class="hint">Les amendements budgétaires sont classés par sujet d'après leur contenu (méthode automatique, voir <a href="/methode/">Méthode</a>).</p>
<h2 class="sec">Les textes</h2><ul class="tx-list">{texts}</ul>
<h2 class="sec">Votes décisifs</h2><div class="list">{"".join(entry(s) for s in finals) or NOFINAL}</div>
<h2 class="sec">Par sujet</h2><ul class="tx-list">{themes}</ul></main></div>'''
        write(f"/budget/{y}/", layout(f"Budget {y} : qui a voté quoi ? · {NAME}", body, desc=f"Tous les votes de l'Assemblée nationale sur le budget {y} (PLF et PLFSS), groupe par groupe.", path=f"/budget/{y}/", current="votes"))
        out.append(f'<li><a href="/budget/{y}/"><b>Budget {y}</b></a> · {len(votes)} scrutins · {len(finals)} votes décisifs</li>')
    body = f'<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Les budgets.</b> Loi de finances et financement de la sécurité sociale, année par année. Une page apparaît automatiquement dès le premier scrutin sur un nouveau budget.</p><ul class="tx-list">{"".join(out)}</ul></main></div>'
    write("/budget/", layout(f"Les budgets : qui a voté quoi ? · {NAME}", body, desc="Les votes de l'Assemblée nationale sur chaque budget, année par année.", path="/budget/", current="votes"))
    return [f"/budget/{y}/" for y in years]

def build_comparer():
    """Comparer deux groupes sur les votes décisifs : côté client, à partir d'un petit JSON."""
    ess = sorted([s for s in S if s["k"] in ("e", "m")], key=lambda s: (s["d"], s["n"]), reverse=True)
    data = {"groupes": ORDER, "noms": GN, "couleurs": COL, "votes": [[s["n"], s["d"], title_of(s)[:110], s["url"].split("/")[2], s["s"], {g: group_pos(s["gm"][g]) for g in ORDER if g in s["gm"]}] for s in ess]}
    write("/api/essentiel-groupes.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    JS = """
(function(){var A=document.getElementById('a'),B=document.getElementById('b'),out=document.getElementById('out'),sum=document.getElementById('sum'),D=null;
var P={pour:'pour',contre:'contre',abstention:'abstention',absent:'absent'};
function fd(d){var m=['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];return parseInt(d.slice(8))+' '+m[parseInt(d.slice(5,7))-1]+' '+d.slice(0,4);}
function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function chip(g,p){var c=D.couleurs[g];var st=p=='pour'?'background:'+c+';color:#fff':p=='contre'?'background:repeating-linear-gradient(-45deg,'+c+' 0 2px,#fff 2px 4px);color:#000;text-shadow:0 0 4px #fff,0 0 4px #fff,0 0 2px #fff':p=='abstention'?'background:repeating-linear-gradient(45deg,'+c+' 0 2px,#fff 2px 5px);color:#000;text-shadow:0 0 4px #fff,0 0 4px #fff,0 0 2px #fff':'background:#fff;box-shadow:inset 0 0 0 1px '+c+';color:#000';return '<span class="pill" style="'+st+'">'+g+' : '+p+'</span>';}
function run(){if(!D)return;var a=A.value,b=B.value;if(a==b){sum.textContent='Choisissez deux groupes différents.';out.innerHTML='';return;}
 var same=0,diff=0,rows=[];D.votes.forEach(function(v){var pa=v[5][a],pb=v[5][b];if(!pa||!pb)return;var opp=(pa=='pour'&&pb=='contre')||(pa=='contre'&&pb=='pour');if(pa==pb)same++;else diff++;if(pa!=pb)rows.push('<li'+(opp?' style="font-weight:600"':'')+'><a href="/vote/'+v[3]+'/">'+esc(v[2])+'</a> <span style="color:var(--muted)">· '+fd(v[1])+' · '+(v[4]?'adopté':'rejeté')+'</span><br>'+chip(a,pa)+' '+chip(b,pb)+'</li>');});
 sum.innerHTML='<b>'+D.noms[a]+'</b> et <b>'+D.noms[b]+'</b> ont pris la même position sur <b>'+same+'</b> votes décisifs et une position différente sur <b>'+diff+'</b> ('+Math.round(100*same/Math.max(1,same+diff))+' % d\\'accord). Ci-dessous, les votes où ils divergent, les oppositions franches en gras.';
 out.innerHTML=rows.join('');history.replaceState(null,'','?a='+a+'&b='+b);}
fetch('/api/essentiel-groupes.json').then(function(r){return r.json();}).then(function(d){D=d;var u=new URLSearchParams(location.search);if(u.get('a'))A.value=u.get('a');if(u.get('b'))B.value=u.get('b');run();});
A.addEventListener('change',run);B.addEventListener('change',run);})();
"""
    opts = lambda sel: "".join(f'<option value="{g}"{" selected" if g==sel else ""}>{g} · {esc(GN[g])}</option>' for g in ORDER)
    body = f'''<div class="grid">{sidebar("essentiels", THEME_COUNTS)}<main class="main"><p class="lede"><b>Comparer deux groupes.</b> Sur les {len(ess)} votes décisifs (lois entières, motions), où sont-ils d'accord, où divergent-ils ?</p>
<p class="hint">Position majoritaire de chaque groupe à chaque scrutin. Règle fixe, aucune sélection. <a href="/methode/">Méthode</a>.</p>
<div class="share" style="gap:12px;flex-wrap:wrap"><select id="a" class="search" style="max-width:300px;margin:0">{opts("RN")}</select><span>contre</span><select id="b" class="search" style="max-width:300px;margin:0">{opts("LFI")}</select></div>
<p id="sum" class="lede" style="font-size:20px;margin-top:18px"></p><ul class="tx-list" id="out"></ul><script>{JS}</script></main></div>'''
    write("/comparer/", layout(f"Comparer deux groupes · {NAME}", body, desc="Comparez les votes de deux groupes de l'Assemblée nationale sur les lois et motions décisives.", path="/comparer/", current="essentiels"))

def build_mon_depute():
    """Mon député : par département, avec photo, groupe et présence."""
    by = collections.defaultdict(list)
    for i, d in enumerate(DEPS):
        if d["dept"] and d["l"] >= LAST_VOTE: by[d["dept"]].append(d)
    def circ_key(d):
        try: return int(d["circo"])
        except Exception: return 999
    sections = []
    for dept in sorted(by, key=norm):
        rows = "".join(f'<li class="dep-row">{photo_tag(d, 40)}<span><a href="{d["url"]}">{esc(d["nom"])}</a> <span style="color:var(--muted)">· {d["circo"]+"ᵉ circonscription · " if d["circo"] else ""}<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{COL[ORDER[d["g"][-1][1]]]}"></span> {ORDER[d["g"][-1][1]]}</span></span></li>' for d in sorted(by[dept], key=circ_key))
        sections.append(f'<details class="dept" id="{slug(dept)}"><summary><b>{esc(dept)}</b> <span style="color:var(--muted)">· {len(by[dept])} député{"s" if len(by[dept])>1 else ""}</span></summary><ul class="tx-list">{rows}</ul></details>')
    ONINPUT = "const q=this.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');document.querySelectorAll('.dept').forEach(d=>{const h=d.textContent.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').includes(q);d.hidden=!h;d.open=q.length>1&&h;})"
    body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Mon député.</b> Cherchez votre département ou votre ville, puis votre circonscription. Députés en exercice uniquement.</p>
<input class="search" type="search" placeholder="Département, ou nom du député" oninput="{esc(ONINPUT)}" style="max-width:100%;font-size:17px;padding:10px 14px">
<p class="hint">Vous ne connaissez pas votre circonscription ? Le site de l'Assemblée la donne à partir de votre adresse : <a href="https://www2.assemblee-nationale.fr/deputes/liste/regions" rel="noopener">assemblee-nationale.fr</a>.</p>
{"".join(sections)}</main></div>'''
    write("/mon-depute/", layout(f"Mon député : qui vote quoi dans ma circonscription ? · {NAME}", body, desc="Trouvez votre député par département et circonscription, et voyez ce qu'il ou elle a voté.", path="/mon-depute/", current="deputes"))

def build_meta(urls):
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{SITE}{u}</loc><lastmod>{BUILD_DATE}</lastmod></url>" for u in urls) + "</urlset>")
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write("/llms.txt", f"""# {NAME}
> Les votes réels de l'Assemblée nationale française (17e législature), scrutin par scrutin, groupe par groupe, député par député. Sans avis, sans note. Source : open data de l'Assemblée nationale, régénéré chaque nuit.

## Pages
- Tous les votes : {SITE}/
- L'essentiel (votes sur l'ensemble d'un texte + motions de censure, règle fixe) : {SITE}/essentiels/ et {SITE}/essentiels/motions-de-censure/
- Un vote : {SITE}/vote/<numéro>-<slug>/ (phrase de synthèse, votes par groupe, vote de chaque député, argument de l'auteur pour un amendement)
- Par sujet : {SITE}/sujet/<sujet>/ — sujets : {", ".join(THEME_LABEL)}
- Par groupe : {SITE}/groupe/<sigle>/, {SITE}/groupe/<sigle>/essentiels/ (votes décisifs) et {SITE}/groupe/<sigle>/<sujet>/ — sigles : {", ".join(g.lower() for g in ORDER)}
- Par député : {SITE}/depute/<slug>-<id>/
- Méthode : {SITE}/methode/
- Cette semaine (7 derniers jours) : {SITE}/cette-semaine/ · Budgets : {SITE}/budget/<année>/ · Comparer deux groupes : {SITE}/comparer/?a=RN&b=LFI · Mon député : {SITE}/mon-depute/ · Statut : {SITE}/statut/ et {SITE}/api/statut.json
- Recherche : {SITE}/recherche/?q=<mots> (index JSON : {SITE}/api/index.json)

## Données brutes
- Députés : {SITE}/api/deputes.json
- Chaque page de vote contient un bloc JSON-LD (schema.org/Article) et une phrase de synthèse en texte brut
- Source officielle d'un scrutin : https://www.assemblee-nationale.fr/dyn/17/scrutins/<numéro>
""")

PHOTOS = os.path.join(ROOT, "data", "raw", "photos")
PHOTO_URL = "https://www2.assemblee-nationale.fr/static/tribun/17/photos/{}.jpg"
def fetch_photos():
    """Photos officielles des députés (© Assemblée nationale). Manquante = silhouette."""
    import urllib.request, concurrent.futures
    os.makedirs(PHOTOS, exist_ok=True)
    def one(d):
        dst = os.path.join(PHOTOS, d["id"] + ".jpg")
        if os.path.exists(dst) and os.path.getsize(dst) > 1000: return True
        try:
            req = urllib.request.Request(PHOTO_URL.format(d["id"].replace("PA", "")), headers={"User-Agent": "ilsvotentquoi.fr (bot photos)"})
            with urllib.request.urlopen(req, timeout=20) as r, open(dst, "wb") as f: f.write(r.read())
            return os.path.getsize(dst) > 1000
        except Exception: return False
    if os.environ.get("IVQ_NO_PHOTOS"): return
    with concurrent.futures.ThreadPoolExecutor(8) as ex: ok = sum(ex.map(one, DEPS))
    print(f"photos : {ok}/{len(DEPS)}", file=sys.stderr)
def has_photo(d): return os.path.exists(os.path.join(PHOTOS, d["id"] + ".jpg"))
def photo_tag(d, size=64):
    if has_photo(d): return f'<img class="photo" src="/photos/{d["id"]}.jpg" alt="" width="{size}" height="{round(size*1.28)}" loading="lazy">'
    return f'<span class="photo silhouette" style="width:{size}px;height:{round(size*1.28)}px"></span>'

def main():
    if os.path.exists(DIST): shutil.rmtree(DIST)
    os.makedirs(DIST); shutil.copytree(STATIC, os.path.join(DIST, "static"))
    fetch_photos()
    if os.path.isdir(PHOTOS): shutil.copytree(PHOTOS, os.path.join(DIST, "photos"))
    build_lists(); build_essentiels(); build_votes(); build_groups(); build_textes(); build_deputes(); build_methode(); build_recherche()
    build_statut(); build_semaine(); build_comparer(); build_mon_depute(); budget_urls = build_budgets()
    urls = ["/", "/essentiels/", "/recherche/", "/cette-semaine/", "/comparer/", "/mon-depute/", "/budget/", "/statut/"] + budget_urls + [ "/essentiels/motions-de-censure/", "/sujets/", "/groupes/", "/deputes/", "/methode/"] + [f"/sujet/{t}/" for t in THEME_LABEL] + [f"/groupe/{g.lower()}/" for g in ORDER] + [f"/groupe/{g.lower()}/essentiels/" for g in ORDER] + \
           [f"/groupe/{g.lower()}/{t}/" for g in ORDER for t in THEME_LABEL] + [s["url"] for s in S] + [d["url"] for d in DEPS] + [f"/texte/{i}-{slug(t,50)}/" for i, t in enumerate(TX)]
    build_meta(urls)
    n = sum(len(f) for _, _, f in os.walk(DIST)); sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DIST) for f in fs)
    print(f"dist/ : {n} fichiers, {sz//1024//1024} Mo", file=sys.stderr)

if __name__ == "__main__": main()
