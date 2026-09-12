#!/usr/bin/env python3
"""
ilsvotentquoi.fr — générateur de site statique.

    python site/build.py            # lit data/site.json, écrit dist/

Une page par scrutin, par sujet, par groupe, par groupe×sujet, par texte de loi, par député.
Tout est du HTML complet (lisible par Google et par les IA), le JavaScript n'ajoute que
l'hémicycle interactif et le tableau nominatif.
"""
import datetime, html, json, math, os, re, shutil, sys, unicodedata

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
BUILD_DATE = datetime.date.today().isoformat()
LAST_VOTE = max(s["d"] for s in S)

def title_of(s):
    """Titre lisible. Amendement : auteur + texte ; sinon intitulé officiel nettoyé."""
    if s["k"] == "a" and s.get("a"):
        a = s["a"]; who = a["au"] + (f" ({a['gr']})" if a["gr"] else "")
        return f"Amendement de {who} · {TX[s['tx']]}"
    return clean_title(s["ti"])

def group_pos(g):
    if g["pour"] + g["contre"] + g["abstention"] == 0: return "absent"
    x = max(g["pour"], g["contre"], g["abstention"])
    return "pour" if x == g["pour"] else "contre" if x == g["contre"] else "abstention"

def sentence(s):
    """Phrase factuelle, générée, pour les moteurs et les IA."""
    res = "adopté" if s["s"] else "rejeté"
    what = title_of(s); what = what[0].lower() + what[1:]
    if s["k"] == "a": what = f"l'{s['ti'][2:]}" if s["ti"].lower().startswith("l'") else s["ti"]
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
  {f'<p class="off">{esc(clean_title(s["ti"]))}</p>' if s['k']=="a" else ""}
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
                  [("votes", "/", "Les votes"), ("sujets", "/sujets/", "Par sujet"), ("groupes", "/groupes/", "Par groupe"), ("deputes", "/deputes/", "Par député"), ("methode", "/methode/", "Méthode")])
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
<link rel="stylesheet" href="/static/style.css">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<script>window.IVQ={{colors:{json.dumps(COL)},names:{json.dumps(GN, ensure_ascii=False)}}};</script>
{ld}{extra_head}
</head>
<body>
<div class="topbar"><span>Assemblée nationale</span><span>17ᵉ législature</span><span>Scrutins publics</span><span>Données à jour au {fdate(LAST_VOTE)}</span></div>
<div class="masthead"><h1 class="brand"><a href="/" style="text-decoration:none">Ils votent <em>quoi</em> ?</a></h1><p class="tag">Les votes réels de chaque groupe et de chaque député, sujet par sujet</p></div>
<div class="subnav"><span class="mini" aria-hidden="true"><a href="/" style="text-decoration:none">Ils votent <em>quoi</em> ?</a></span>{nav}</div>
<div class="wrap">{body}</div>
<footer class="note" style="max-width:1180px;margin:48px auto 0;padding:16px 16px 40px"><p><b>{NAME}</b> — un outil indépendant et sans parti pris. Source : open data de l'Assemblée nationale, mis à jour chaque nuit. Chaque vote renvoie au scrutin officiel. <a href="/methode/">Méthode</a> · <a href="/llms.txt">Données pour les IA</a> · <a href="/sitemap.xml">Plan du site</a>. Généré le {fdate(BUILD_DATE)}.</p></footer>
<script src="/static/hemi.js" defer></script>
</body></html>'''

def sidebar(current=None, counts=None):
    CUR = ' aria-current="page"'
    items = [f'<a class="subj" href="/"{CUR if current=="all" else ""}><span>Tous les votes</span><small>{len(S)}</small></a>']
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
def page_list(items, base, current, lede, desc, title, page=1):
    chunk, pager, n = paginate(items, base, page)
    body = f'''<div class="grid">{sidebar(current, THEME_COUNTS)}<main class="main">
<p class="lede">{lede}</p><p class="dek">{esc(desc)}</p>
<div class="list">{"".join(entry(s) for s in chunk)}</div>{pager}</main></div>'''
    path = base if page == 1 else f"{base}page/{page}/"
    write(path, layout(title if page == 1 else f"{title} · page {page}", body, desc=desc, path=path, current="votes" if current=="all" else "sujets"))
    return n

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
  {f'<p class="off">{esc(clean_title(s["ti"]))}</p>' if s['k']=="a" else ""}
  <div class="result"><span class="pill {'ok' if ok else 'no'}">{'Adopté' if ok else 'Rejeté'}</span><span class="tally"><b>{s['t'][0]}</b> pour · <b>{s['t'][1]}</b> contre · <b>{s['t'][2]}</b> abst.</span><span>{s['v']} votants sur 577</span></div>
  <p class="summary-text">{sentence(s)}</p>
  <div class="share"><button type="button" data-share>Partager</button><a href="/og/{s['n']}.png" download>Image pour les réseaux</a><a href="https://www.assemblee-nationale.fr/dyn/17/scrutins/{s['n']}" rel="noopener" target="_blank">Scrutin officiel ↗</a></div>
  <div class="hlegend" style="margin-top:18px"><span>● Pour</span><span>⊗ Contre</span><span>▨ Abstention</span><span>○ Absent ou non-votant</span><span>· couleur = groupe</span><label class="toggle" style="margin-left:auto"><input type="checkbox" id="cvd"> Couleurs adaptées</label></div>
  <div class="hemi-wrap" data-vote="{s['vote']}" data-date="{s['d']}"><noscript>Activez JavaScript pour l'hémicycle interactif ; le détail par député est dans le tableau ci-dessous.</noscript></div>
  {group_table(s)}
  {why}
  <h2 class="sec">Le vote de chaque député</h2>
  <div id="deps"><p class="hint">Chargement du tableau nominatif…</p></div>
</article></main></div>'''
        write(s["url"], layout(f"{q} · {NAME}", body, desc=desc, path=s["url"], jsonld=jsonld, og_image=f"{SITE}/og/{s['n']}.png", current="votes"))

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

def build_deputes():
    LBL = {"P": "pour", "C": "contre", "A": "abstention", "N": "non-votant"}
    rows_index = []
    for i, d in enumerate(DEPS):
        my = []; cnt = {"P": 0, "C": 0, "A": 0, "N": 0}; present = 0; eligible = 0
        for s in S:
            v = s["vote"][i] if i < len(s["vote"]) else "."
            if d["f"] <= s["d"] <= d["l"]: eligible += 1
            if v != ".": cnt[v] += 1; present += v in "PCA"
            if v != "." and s["k"] != "a": my.append((s, v))
        my.sort(key=lambda x: x[0]["d"], reverse=True)
        gid = ORDER[d["g"][-1][1]]
        rate = round(100 * present / max(1, eligible))
        table = "".join(f'<tr><td><a href="{s["url"]}">{esc(title_of(s))}</a></td><td>{fdate(s["d"])}</td><td class="v">{LBL[v]}</td><td>{"adopté" if s["s"] else "rejeté"}</td></tr>' for s, v in my)
        body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="crumbs"><a href="/deputes/">Députés</a> › {esc(d['nom'])}</p>
<p class="lede"><b>{esc(d['nom'])}</b>{(", "+esc(d['dept'])+(" ("+d['circo']+"ᵉ circonscription)" if d['circo'] else "")) if d['dept'] else ""}. Groupe <a href="/groupe/{gid.lower()}/"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{COL[gid]};vertical-align:middle"></span> {esc(GN[gid])}</a>.</p>
<div class="stat-row"><div class="stat"><b>{rate} %</b><span>de présence aux scrutins publics</span></div><div class="stat"><b>{cnt['P']}</b><span>votes pour</span></div><div class="stat"><b>{cnt['C']}</b><span>votes contre</span></div><div class="stat"><b>{cnt['A']}</b><span>abstentions</span></div></div>
<p class="hint">Présence = a pris part au vote (pour, contre ou abstention) sur les {eligible} scrutins tenus pendant son mandat. Le tableau liste les votes sur les textes entiers, articles et motions ; les votes sur amendements sont consultables scrutin par scrutin.</p>
<table class="deps"><thead><tr><th>Vote</th><th>Date</th><th>Position</th><th>Résultat</th></tr></thead><tbody>{table}</tbody></table></main></div>'''
        jsonld = {"@context": "https://schema.org", "@type": "Person", "name": d["nom"], "jobTitle": "Député·e", "memberOf": {"@type": "Organization", "name": GN[gid]}, "url": SITE + d["url"]}
        write(d["url"], layout(f"{d['nom']} : ses votes à l'Assemblée · {NAME}", body, desc=f"Les votes de {d['nom']} ({gid}) à l'Assemblée nationale : présence {rate} %, {cnt['P']} pour, {cnt['C']} contre, {cnt['A']} abstentions.", path=d["url"], jsonld=jsonld, current="deputes"))
        rows_index.append((d["famille"] or d["nom"], f'<li><a href="{d["url"]}">{esc(d["nom"])}</a> <span style="color:var(--muted)">· {gid}{(" · "+esc(d["dept"])) if d["dept"] else ""} · présence {rate} %</span></li>'))
    rows_index.sort(key=lambda x: norm(x[0]))
    ONINPUT = "const q=this.value.toLowerCase();document.querySelectorAll('.tx-list li').forEach(l=>l.hidden=!l.textContent.toLowerCase().includes(q))"
    body = f'<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Par député.</b> {len(DEPS)} députés ayant siégé pendant la législature.</p><input class="search" type="search" placeholder="Nom, département, groupe" oninput="{esc(ONINPUT)}"><ul class="tx-list">{"".join(r for _, r in rows_index)}</ul></main></div>'
    write("/deputes/", layout(f"Les votes par député · {NAME}", body, desc="Retrouvez votre député et ce qu'il ou elle a voté.", path="/deputes/", current="deputes"))
    write("/api/deputes.json", json.dumps([{"id": d["id"], "nom": d["nom"], "dept": d["dept"], "circo": d["circo"], "g": d["g"], "f": d["f"], "l": d["l"], "slug": d["slug"]} for d in DEPS], ensure_ascii=False, separators=(",", ":")))

def build_methode():
    body = f'''<div class="grid">{sidebar(None, THEME_COUNTS)}<main class="main"><p class="lede"><b>Méthode.</b> Comment ce site est fabriqué, et ce qu'il ne fait pas.</p>
<div class="qa"><h2>D'où viennent les chiffres</h2><p>De l'open data de l'Assemblée nationale : scrutins, amendements, dossiers législatifs et liste des députés de la 17ᵉ législature. Le site est régénéré chaque nuit. Chaque page de vote renvoie au scrutin officiel. Les groupes sont affichés dans l'ordre de l'hémicycle, de gauche à droite, avec les couleurs que l'Assemblée publie elle-même. « Absent » = membres du groupe moins votants et non-votants déclarés.</p></div>
<div class="qa"><h2>Comment les votes sont rangés par sujet</h2><p>Chaque vote est rattaché à son texte de loi ; chaque texte est classé dans un à trois sujets (liste publique, corrigeable). Pour les budgets, qui touchent à tout, chaque amendement est classé d'après son contenu par mots-clés. Le classement est automatique ; les erreurs peuvent être signalées et sont corrigées dans le fichier public de classement.</p></div>
<div class="qa"><h2>« L'auteur explique »</h2><p>Pour un amendement, la phrase affichée est l'exposé sommaire écrit par le député qui l'a déposé. C'est son argument, pas une description neutre : il est cité comme tel, avec son nom et son groupe.</p></div>
<div class="qa"><h2>L'hémicycle</h2><p>Un point par député, couleur du groupe, texture du vote : plein = pour, croix = contre, hachures = abstention, vide = absent ou non-votant. Les députés sont placés par groupe, de gauche à droite ; la place d'un point n'est pas le siège réel. Le bouton « couleurs adaptées » remplace la palette officielle par une palette lisible pour les daltoniens.</p></div>
<div class="qa"><h2>Ce que le site ne fait pas</h2><p>Il ne dit pas si un vote est une avancée ou un recul. Il ne choisit pas les sujets selon un programme. Il ne résume pas les textes à la place de leurs auteurs. Il n'a pas de compte à rendre à un parti, un média ou un financeur.</p></div>
</main></div>'''
    write("/methode/", layout(f"Méthode · {NAME}", body, desc="Comment ilsvotentquoi.fr est fabriqué : sources, classement par sujet, neutralité.", path="/methode/", current="methode"))

def build_meta(urls):
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{SITE}{u}</loc><lastmod>{BUILD_DATE}</lastmod></url>" for u in urls) + "</urlset>")
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write("/llms.txt", f"""# {NAME}
> Les votes réels de l'Assemblée nationale française (17e législature), scrutin par scrutin, groupe par groupe, député par député. Sans avis, sans note. Source : open data de l'Assemblée nationale, régénéré chaque nuit.

## Pages
- Tous les votes : {SITE}/
- Un vote : {SITE}/vote/<numéro>-<slug>/ (phrase de synthèse, votes par groupe, vote de chaque député, argument de l'auteur pour un amendement)
- Par sujet : {SITE}/sujet/<sujet>/ — sujets : {", ".join(THEME_LABEL)}
- Par groupe : {SITE}/groupe/<sigle>/ et {SITE}/groupe/<sigle>/<sujet>/ — sigles : {", ".join(g.lower() for g in ORDER)}
- Par député : {SITE}/depute/<slug>-<id>/
- Méthode : {SITE}/methode/

## Données brutes
- Députés : {SITE}/api/deputes.json
- Chaque page de vote contient un bloc JSON-LD (schema.org/Article) et une phrase de synthèse en texte brut
- Source officielle d'un scrutin : https://www.assemblee-nationale.fr/dyn/17/scrutins/<numéro>
""")

def main():
    if os.path.exists(DIST): shutil.rmtree(DIST)
    os.makedirs(DIST); shutil.copytree(STATIC, os.path.join(DIST, "static"))
    build_lists(); build_votes(); build_groups(); build_textes(); build_deputes(); build_methode()
    urls = ["/", "/sujets/", "/groupes/", "/deputes/", "/methode/"] + [f"/sujet/{t}/" for t in THEME_LABEL] + [f"/groupe/{g.lower()}/" for g in ORDER] + \
           [f"/groupe/{g.lower()}/{t}/" for g in ORDER for t in THEME_LABEL] + [s["url"] for s in S] + [d["url"] for d in DEPS] + [f"/texte/{i}-{slug(t,50)}/" for i, t in enumerate(TX)]
    build_meta(urls)
    n = sum(len(f) for _, _, f in os.walk(DIST)); sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DIST) for f in fs)
    print(f"dist/ : {n} fichiers, {sz//1024//1024} Mo", file=sys.stderr)

if __name__ == "__main__": main()
