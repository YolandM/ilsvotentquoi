#!/usr/bin/env python3
"""
ilsvotentquoi.fr — pipeline de données.

    python pipeline/run.py fetch      # télécharge l'open data de l'Assemblée (4 zips)
    python pipeline/run.py build      # index + appariement + classement → data/site.json
    python pipeline/run.py all        # les deux

Sources (17e législature) : data.assemblee-nationale.fr
  - Scrutins.json.zip                         : chaque scrutin public, votes par groupe et nominatifs
  - Amendements.json.zip                      : texte + exposé sommaire de chaque amendement
  - Dossiers_Legislatifs.json.zip             : textes de loi (titres)
  - AMO10_deputes_actifs_mandats_actifs_organes.json.zip : députés en exercice, groupes (couleurs officielles)

Aucune dépendance hors bibliothèque standard.
"""
import collections, glob, html, io, json, os, re, sqlite3, sys, unicodedata, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data")
LEG = "17"
BASE = f"https://data.assemblee-nationale.fr/static/openData/repository/{LEG}"
SOURCES = {
    "scrutins":    f"{BASE}/loi/scrutins/Scrutins.json.zip",
    "amendements": f"{BASE}/loi/amendements_div_legis/Amendements.json.zip",
    "dossiers":    f"{BASE}/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip",
    "amo":         f"{BASE}/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip",
}
ORDER = ["LFI", "GDR", "ECO", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDR", "RN", "NI"]
# codes organe → sigle court (les groupes changent d'uid quand ils se reconstituent)
GROUPS = {"PO845401": "RN", "PO845407": "EPR", "PO845413": "LFI", "PO845419": "SOC", "PO845425": "DR",
          "PO845439": "ECO", "PO845454": "DEM", "PO845470": "HOR", "PO845485": "LIOT", "PO845514": "GDR",
          "PO847173": "UDR", "PO872880": "UDR", "PO840056": "NI"}

def log(*a): print(*a, file=sys.stderr, flush=True)
def s_(v):
    """Les champs vides de l'AN sont des dicts {'@xsi:nil': 'true'} : on veut None."""
    if isinstance(v, dict): return v.get("#text")
    return v if isinstance(v, str) else None
def norm(s): return re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode())
def strip_html(h):
    h = s_(h) or ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(h))).strip()
def slugify(s, n=70):
    s = norm(s).strip(); s = re.sub(r"\s+", "-", s); return s[:n].rstrip("-")

# ----------------------------------------------------------------------------- fetch
def fetch():
    os.makedirs(RAW, exist_ok=True)
    for name, url in SOURCES.items():
        dest = os.path.join(RAW, name)
        log(f"↓ {name}  {url}")
        with urllib.request.urlopen(url, timeout=600) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(dest)
        log(f"  ok, {len(data)//1024//1024} Mo")

# ----------------------------------------------------------------------------- build
def load_scrutins():
    rows = {}
    for f in glob.iglob(os.path.join(RAW, "scrutins", "**", "*.json"), recursive=True):
        s = json.load(open(f, encoding="utf-8"))["scrutin"]
        t = s["titre"]
        kind = ("amendement" if re.match(r"^l['’](sous-)?amendement", t, re.I) else
                "article" if re.match(r"^l['’]article", t, re.I) else
                "ensemble" if "ensemble" in t[:15] else
                "motion" if "motion" in t[:15] else "autre")
        d = (s["objet"].get("dossierLegislatif") or {}).get("libelle")
        if not d:
            m = re.search(r"(projet de loi|proposition de loi|proposition de résolution)(.*?)(?:\s*\((?:première|deuxième|nouvelle|troisième|texte|lecture|examen)[^)]*\)\s*\.?\s*$|\.?\s*$)", t, re.I)
            d = (m.group(0).strip().rstrip(".") if m else t[:120])
            d = re.sub(r"\s*\((?:première|deuxième|nouvelle|troisième|texte de la commission mixte paritaire|lecture définitive)[^)]*\)\.?$", "", d)
        sv = s["syntheseVote"]["decompte"]
        groups, nominal = [], {}
        for g in s["ventilationVotes"]["organe"]["groupes"]["groupe"]:
            gid = GROUPS.get(g["organeRef"])
            if not gid: continue
            dv = g["vote"]["decompteVoix"]
            groups.append({"id": gid, "pour": int(dv["pour"]), "contre": int(dv["contre"]), "abstention": int(dv["abstentions"]),
                           "nonVotant": int(dv["nonVotants"]), "membres": int(g["nombreMembresGroupe"])})
            dn = g["vote"]["decompteNominatif"]
            for key, letter in (("pours", "P"), ("contres", "C"), ("abstentions", "A"), ("nonVotants", "N")):
                x = dn.get(key)
                if not x: continue
                vs = x["votant"]; vs = vs if isinstance(vs, list) else [vs]
                for e in vs: nominal[e["acteurRef"]] = (letter, gid)
        rows[int(s["numero"])] = {
            "n": int(s["numero"]), "date": s["dateScrutin"], "titre": t, "sort": s["sort"]["code"], "kind": kind,
            "textkey": d, "seance": s.get("seanceRef"), "votants": int(s["syntheseVote"]["nombreVotants"]),
            "pour": int(sv["pour"]), "contre": int(sv["contre"]), "abstention": int(sv["abstentions"]),
            "groupes": groups, "nominal": nominal,
        }
    log(f"scrutins : {len(rows)}")
    return rows

def load_amendements():
    """Index léger : uid → (numéro, texte, séance, auteur, dispositif, exposé, groupe auteur)."""
    idx, by_num = {}, collections.defaultdict(list)
    n = 0
    for f in glob.iglob(os.path.join(RAW, "amendements", "**", "*.json"), recursive=True):
        try: a = json.load(open(f, encoding="utf-8"))["amendement"]
        except Exception: continue
        ident = a.get("identification") or {}; sig = a.get("signataires") or {}; au = sig.get("auteur") or {}
        corps = ((a.get("corps") or {}).get("contenuAuteur") or {})
        num = s_(ident.get("numeroLong"));
        if not num: continue
        rec = {"uid": s_(a["uid"]), "num": num, "texte": s_(a.get("texteLegislatifRef")), "seance": s_(a.get("seanceDiscussionRef")),
               "auteur": strip_html(sig.get("libelle"))[:200], "groupe": GROUPS.get(s_(au.get("groupePolitiqueRef")) or "", None),
               "gouv": s_(au.get("typeAuteur")) == "Gouvernement",
               "dispositif": strip_html(corps.get("dispositif"))[:1200], "expose": strip_html(corps.get("exposeSommaire"))[:2500]}
        idx[rec["uid"]] = rec
        by_num[num].append(rec)
        m = re.match(r"^(I|II)-(\d+)$", num)        # loi de finances : I-2085 / II-2085
        if m: by_num[m.group(2)].append(rec)
        n += 1
    log(f"amendements : {n}")
    return idx, by_num

def load_documents():
    doc = {}
    for f in glob.iglob(os.path.join(RAW, "dossiers", "**", "document", "*.json"), recursive=True):
        d = json.load(open(f, encoding="utf-8"))["document"]
        t = (d.get("titres") or {}).get("titrePrincipal")
        if isinstance(t, str): doc[s_(d["uid"])] = set(norm(t).split())
    return doc

def load_acteurs():
    acts, groups = {}, {}
    for f in glob.iglob(os.path.join(RAW, "amo", "**", "acteur", "*.json"), recursive=True):
        a = json.load(open(f, encoding="utf-8"))["acteur"]; i = a["etatCivil"]["ident"]
        m = a["mandats"]["mandat"]; m = m if isinstance(m, list) else [m]
        dep = next((x for x in m if x.get("typeOrgane") == "ASSEMBLEE" and not s_(x.get("dateFin"))), None)
        lieu = ((dep or {}).get("election") or {}).get("lieu") or {}
        acts[s_(a["uid"])] = {"nom": f"{i['civ']} {i['prenom']} {i['nom']}", "prenom": i["prenom"], "famille": i["nom"],
                              "dept": s_(lieu.get("departement")), "circo": s_(lieu.get("numCirco"))}
    for f in glob.iglob(os.path.join(RAW, "amo", "**", "organe", "*.json"), recursive=True):
        o = json.load(open(f, encoding="utf-8"))["organe"]
        if o.get("codeType") == "GP" and s_(o["uid"]) in GROUPS:
            groups[GROUPS[s_(o["uid"])]] = {"id": GROUPS[s_(o["uid"])], "nom": s_(o.get("libelle")), "abrev": s_(o.get("libelleAbrev")),
                                            "couleur": s_(o.get("couleurAssociee"))}
    log(f"députés : {len(acts)}, groupes : {len(groups)}")
    return acts, groups

def match(scrutins, by_num, doc):
    """Relie un scrutin sur amendement à l'amendement : numéro + séance + titre du texte + nom de l'auteur."""
    ok = weak = none = 0
    for s in scrutins.values():
        if s["kind"] != "amendement": continue
        t = s["titre"]
        m = re.match(r"^l['’](?:sous-)?amendement(?: de suppression| de rédaction globale)? n°\s*([0-9]+)(?: \(rect\.\))?(?: (?:de |du )(?:M\. |Mme )?([^,(]+?))?(?= et | à | après | avant |,|\(|$)", t, re.I)
        if not m: none += 1; continue
        num = m.group(1); name = norm(m.group(2) or "").split(); name = name[-1] if name else ""
        tm = re.search(r"(projet de loi|proposition de loi|proposition de résolution)(.*?)(?:\(|$)", t, re.I)
        words = set(norm(tm.group(0)).split()) if tm else set()
        best, bs = None, -1
        for rec in by_num.get(num, []):
            sc = 0
            if rec["seance"] and rec["seance"] == s["seance"]: sc += 3
            sim = len(words & doc.get(rec["texte"], set())) / max(len(words), 1); sc += 2 * sim
            aut = norm(rec["auteur"])
            if name and name in aut: sc += 2
            if name == "gouvernement" and rec["gouv"]: sc += 2
            if sc > bs: bs, best = sc, rec
        if best and bs >= 2.2:
            s["amdt"] = best["uid"]; s["amdt_sur"] = bs >= 4
            ok += bs >= 4; weak += bs < 4
        else: none += 1
    log(f"appariement amendements : {ok} sûrs, {weak} probables, {none} sans")

KW = {
 "pouvoir-achat": r"pouvoir d.achat|smic|bas salaires|tva\b|prix de|cheque|prime de |allocation|aide personnalisee|apl\b|minima sociaux|rsa\b|bareme de l.impot sur le revenu|tranche|credit d.impot pour les menages|carburant|facture|energie des menages|tarif|panier|inflation|indexation|pension de retraite|revalorisation des pensions|bourses|precarite|pauvrete|prestations familiales|aah\b",
 "fiscalite-riches": r"ultra-riches|ultra riches|hauts patrimoines|grandes fortunes|isf\b|impot sur la fortune|zucman|holding|dividendes|plus-values|flat tax|prelevement forfaitaire unique|niche fiscale|optimisation fiscale|evasion fiscale|fraude fiscale|paradis fisca|multinationale|superprofits|rachats d.actions|successions|droits de succession|exit tax|impot sur les societes|grandes entreprises|cvae\b|pacte dutreil|contribution exceptionnelle",
 "travail-retraites": r"retraite|age legal|duree de cotisation|chomage|assurance chomage|salari|code du travail|apprentissage|heures supplementaires|emploi\b|conditions de travail|penibilite|syndic|licenciement|travailleurs|independants|auto-entrepreneur|arret de travail|jours de carence",
 "sante": r"\bsante\b|hopital|hospitali|medecin|soins|medicament|maladie|securite sociale|ondam|assurance maladie|franchise|handicap|fin de vie|aide a mourir|psychiatri|cancer|tabac|alcool|vaccin|ehpad|dependance|autonomie|pharma",
 "education": r"\becole|enseign|universit|etudiant|eleve|jeunesse|petite enfance|creche|recherche|lycee|college|formation",
 "ecologie-energie": r"climat|carbone|ecolog|biodiversit|pollution|nucleaire|renouvelable|eolien|photovolta|energie|transition|renovation thermique|passoire|transport|ferroviaire|sncf|velo|voiture|automobile|pesticide|eau\b|foret|dechet|plastique|environnement",
 "agriculture-alimentation": r"agric|paysan|elevage|pesticide|alimenta|peche\b|pecheur|viticol|vin\b|egalim|msa\b|foncier agricole|cantine",
 "securite-justice": r"police|gendarm|justice|prison|penal|delinquan|terroris|narcotrafic|drogue|stupefiant|securite interieure|magistrat|tribunal|peine|recidiv|ordre public|violence",
 "immigration": r"immigr|etranger|asile|nationalite|titre de sejour|ofii|ofpra|aide medicale d.etat|ame\b|regularisation|frontiere|naturalisation",
 "logement-territoires": r"logement|loyer|hlm|bailleur|urbanisme|collectivit|commune|departement|region|intercommunal|dgf\b|dotation|ruralit|zrr|maire|territoire",
 "economie-entreprises": r"entreprise|pme\b|tpe\b|industri|commerce|simplification|dette|deficit|credit d.impot recherche|cir\b|banque|assurance|investissement|competitivite|start-up|innovation|exportation|douane",
 "institutions-libertes": r"election|parlement|senat|constitution|referendum|vie privee|donnees personnelles|numerique|libertes|elu local|scrutin|democratie|laicite|cumul|transparence|lobby",
 "egalite-droits": r"femmes|egalite entre|discrimination|lgbt|homophob|sexiste|sexuel|feminicide|parite|transgenre|racisme|antisemit",
 "international-defense": r"defense|armee|militaire|otan|ukraine|europe|union europeenne|etranger|diplomat|aide publique au developpement|francophonie|israel|palestin",
 "outre-mer": r"outre-mer|mayotte|corse|caledonie|guadeloupe|martinique|reunion|guyane|polynesie|ultramarin",
 "culture-sport-medias": r"culture|sport|audiovisuel|media|cinema|patrimoine|musee|livre|presse|jeux olympiques|france televisions|radio",
}
KW = {k: re.compile(v) for k, v in KW.items()}

def classify(scrutins, amdts):
    """Thème du texte parent (pipeline/textes_themes.json, éditable à la main) ;
    pour les textes transversaux (budgets) et tous les amendements, on ajoute les thèmes détectés dans le contenu."""
    tt = json.load(open(os.path.join(ROOT, "pipeline", "textes_themes.json"), encoding="utf-8"))
    unknown = collections.Counter()
    for s in scrutins.values():
        meta = tt.get(s["textkey"])
        if not meta:
            unknown[s["textkey"]] += 1
            meta = {"themes": ["institutions-libertes"], "transversal": False}
        themes = list(meta["themes"]); method = "texte"
        a = amdts.get(s.get("amdt"))
        if a:
            txt = norm(a["dispositif"] + " " + a["expose"])[:2500]
            scores = sorted(((len(rx.findall(txt)), k) for k, rx in KW.items() if rx.search(txt)), reverse=True)
            found = [k for v, k in scores if v >= 2][:2]
            if meta.get("transversal"):
                themes = found or ["economie-entreprises"]; method = "amendement" if found else "budget-non-classe"
            else:
                for k in found:
                    if k not in themes: themes.append(k)
                method = "texte+amendement" if found else "texte"
        s["themes"] = themes; s["method"] = method
    if unknown:
        log(f"⚠ {len(unknown)} textes sans thème dans textes_themes.json (ajoutez-les) :")
        for k, v in unknown.most_common(20): log(f"   {v:4}  {k[:100]}")
    json.dump({k: v for k, v in unknown.items()}, open(os.path.join(OUT, "textes_sans_theme.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def build():
    os.makedirs(OUT, exist_ok=True)
    scrutins = load_scrutins()
    amdts, by_num = load_amendements()
    doc = load_documents()
    acts, groups = load_acteurs()
    match(scrutins, by_num, doc)
    classify(scrutins, amdts)

    # députés : ordre stable, groupe par date (segments), première/dernière participation
    timeline = collections.defaultdict(dict); first = {}; last = {}
    for s in scrutins.values():
        for dep, (letter, gid) in s["nominal"].items():
            timeline[dep][s["date"]] = gid
            first[dep] = min(first.get(dep, s["date"]), s["date"]); last[dep] = max(last.get(dep, s["date"]), s["date"])
    deps = sorted(timeline)
    DI = {d: i for i, d in enumerate(deps)}
    deputes = []
    for d in deps:
        seg, lastg = [], None
        for date, g in sorted(timeline[d].items()):
            if g != lastg: seg.append([date, ORDER.index(g)]); lastg = g
        a = acts.get(d, {})
        deputes.append({"id": d, "nom": a.get("nom") or "Ancien·ne député·e", "prenom": a.get("prenom"), "famille": a.get("famille"),
                        "dept": a.get("dept"), "circo": a.get("circo"), "g": seg, "f": first[d], "l": last[d],
                        "slug": slugify(a.get("nom") or d)})

    textes = sorted({s["textkey"] for s in scrutins.values()})
    TI = {t: i for i, t in enumerate(textes)}
    out_s = []
    for n in sorted(scrutins):
        s = scrutins[n]
        o = {"n": n, "d": s["date"], "k": s["kind"][0], "s": 1 if s["sort"] == "adopté" else 0, "v": s["votants"],
             "t": [s["pour"], s["contre"], s["abstention"]], "th": s["themes"], "tx": TI[s["textkey"]], "ti": s["titre"],
             "g": [[g["id"], g["pour"], g["contre"], g["abstention"], g["nonVotant"], g["membres"]] for g in s["groupes"]],
             "vote": "".join(s["nominal"].get(d, (".",))[0] for d in deps)}
        a = amdts.get(s.get("amdt"))
        if a:
            o["a"] = {"au": a["auteur"].split(",")[0].strip()[:60], "gr": a["groupe"] or ("GOUV" if a["gouv"] else ""),
                      "ex": a["expose"], "di": a["dispositif"], "sur": bool(s.get("amdt_sur"))}
        out_s.append(o)
    site = {"legislature": LEG, "textes": textes, "scrutins": out_s, "deputes": deputes,
            "groupes": [groups[g] for g in ORDER if g in groups], "themes": json.load(open(os.path.join(ROOT, "pipeline", "themes.json"), encoding="utf-8"))}
    json.dump(site, open(os.path.join(OUT, "site.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"→ data/site.json : {len(out_s)} scrutins, {len(deputes)} députés, {os.path.getsize(os.path.join(OUT,'site.json'))//1024//1024} Mo")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("fetch", "all"): fetch()
    if cmd in ("build", "all"): build()
