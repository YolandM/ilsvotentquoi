#!/usr/bin/env python3
"""
ilsvotentquoi.fr — cartes de partage (PNG) pour chaque vote.

    python site/cards.py            # écrit dist/og/<numéro>.png (1200×630) et dist/og/<numéro>-story.png (1080×1920)
    python site/cards.py --only-og  # seulement le format lien (plus rapide)

Dessin direct avec Pillow : hémicycle par groupe (couleur = groupe, texture = vote), titre, résultat, source.
"""
import json, math, os, re, sys, unicodedata
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "data", "site.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "dist", "og"); os.makedirs(OUT, exist_ok=True)
ORDER = ["LFI", "GDR", "ECO", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDR", "RN", "NI"]
COL = {g["id"]: g["couleur"] for g in D["groupes"]}
TX, DEPS = D["textes"], D["deputes"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
def font(name, size):
    for p in (os.path.join(ROOT, "site", "fonts", name), os.path.join(FONT_DIR, {"serif-bold": "DejaVuSerif-Bold.ttf", "serif": "DejaVuSerif.ttf", "sans": "DejaVuSans.ttf", "sans-bold": "DejaVuSans-Bold.ttf"}.get(name, name))):
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def fdate(d): y, m, dd = d.split("-"); return f"{int(dd)} {MONTHS[int(m)-1]} {y}"
def clean_title(t): return re.sub(r"\s*\((première|deuxième|nouvelle|troisième)[^)]*\)\.?$", "", t).rstrip(".")
def title_of(s):
    if s["k"] == "a" and s.get("a"):
        a = s["a"]; return f"Amendement de {a['au']}" + (f" ({a['gr']})" if a["gr"] else "") + f" · {TX[s['tx']]}"
    t = clean_title(s["ti"]); return t[0].upper() + t[1:]
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

def hex2rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def draw_hemi(img, s, x0, y0, w):
    """Dessine l'hémicycle dans un carré de largeur w (coordonnées 600×300 mises à l'échelle)."""
    sc = w / 600; d = ImageDraw.Draw(img); r = 6.2 * sc
    for k, (g, vote, _) in enumerate(people(s)[:577]):
        sx, sy, _ = SEATS[k]; x, y = x0 + sx * sc, y0 + sy * sc; c = hex2rgb(COL[g])
        if vote == "P": d.ellipse((x-r, y-r, x+r, y+r), fill=c)
        elif vote == "C":
            d.ellipse((x-r, y-r, x+r, y+r), fill=c); k2 = r * 0.42
            d.line((x-k2, y-k2, x+k2, y+k2), fill="white", width=max(1, int(1.7*sc))); d.line((x+k2, y-k2, x-k2, y+k2), fill="white", width=max(1, int(1.7*sc)))
        elif vote == "A":
            light = tuple(int(v + (255 - v) * 0.55) for v in c); d.ellipse((x-r, y-r, x+r, y+r), fill=light, outline=c, width=max(1, int(1.2*sc)))
        else: d.ellipse((x-r, y-r, x+r, y+r), fill="white", outline=c, width=max(1, int(1.2*sc)))

def wrap(text, f, maxw, draw):
    words = text.split(); lines = []; cur = ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if draw.textlength(t, font=f) <= maxw: cur = t
        else: lines.append(cur); cur = wd
    if cur: lines.append(cur)
    return lines

def card_og(s):
    W, H = 1200, 630; img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 8), fill="black")
    ft = font("serif-bold", 40); fs = font("sans", 22); fb = font("sans-bold", 22); fk = font("sans", 18)
    d.text((56, 40), f"{fdate(s['d']).upper()}  ·  ASSEMBLÉE NATIONALE  ·  SCRUTIN Nº {s['n']}", font=fk, fill=(130, 130, 130))
    lines = wrap(title_of(s), ft, 620, d)
    if len(lines) > 4: lines = lines[:4]; lines[-1] = lines[-1].rstrip(" ,;:") + "…"
    y = 80
    for ln in lines: d.text((56, y), ln, font=ft, fill="black"); y += 50
    res = "ADOPTÉ" if s["s"] else "REJETÉ"; rc = (30, 122, 74) if s["s"] else (185, 29, 71)
    y += 12; d.rounded_rectangle((56, y, 56 + 130, y + 40), radius=20, fill=rc); d.text((56 + 65, y + 20), res, font=fb, fill="white", anchor="mm")
    d.text((56 + 150, y + 8), f"{s['t'][0]} pour · {s['t'][1]} contre · {s['t'][2]} abst. · {s['v']} votants", font=fs, fill="black")
    draw_hemi(img, s, 660, 70, 500)
    # légende couleurs
    x = 56; y = H - 90
    for g in ORDER:
        if g not in s.get("gmset", set(gg[0] for gg in s["g"])): continue
        d.ellipse((x, y+4, x+14, y+18), fill=hex2rgb(COL[g])); d.text((x+20, y), g, font=fk, fill="black"); x += 30 + d.textlength(g, font=fk) + 18
    d.text((56, H - 48), "● pour   ⊗ contre   ◐ abstention   ○ absent", font=fk, fill=(130, 130, 130))
    d.text((W - 56, H - 48), "ilsvotentquoi.fr", font=font("serif-bold", 26), fill="black", anchor="ra")
    img.save(os.path.join(OUT, f"{s['n']}.png"), optimize=True)

def card_story(s):
    W, H = 1080, 1920; img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 14), fill="black")
    ft = font("serif-bold", 60); fs = font("sans", 30); fb = font("sans-bold", 30); fk = font("sans", 26)
    d.text((70, 120), f"{fdate(s['d']).upper()}  ·  SCRUTIN Nº {s['n']}", font=fk, fill=(130, 130, 130))
    y = 180
    for ln in wrap(title_of(s), ft, 940, d)[:6]: d.text((70, y), ln, font=ft, fill="black"); y += 74
    res = "ADOPTÉ" if s["s"] else "REJETÉ"; rc = (30, 122, 74) if s["s"] else (185, 29, 71)
    y += 20; d.rounded_rectangle((70, y, 70 + 190, y + 56), radius=28, fill=rc); d.text((70 + 95, y + 28), res, font=fb, fill="white", anchor="mm")
    d.text((70 + 210, y + 12), f"{s['t'][0]} pour · {s['t'][1]} contre · {s['t'][2]} abst.", font=fs, fill="black")
    draw_hemi(img, s, 60, 760, 960)
    x = 70; y = 1330
    for g in ORDER:
        if g not in set(gg[0] for gg in s["g"]): continue
        d.ellipse((x, y+6, x+20, y+26), fill=hex2rgb(COL[g])); d.text((x+28, y), g, font=fk, fill="black"); x += 40 + d.textlength(g, font=fk) + 26
        if x > 900: x = 70; y += 44
    d.text((70, y + 60), "● pour   ⊗ contre   ◐ abstention   ○ absent", font=fk, fill=(130, 130, 130))
    d.text((W // 2, H - 150), "Ils votent quoi ?", font=font("serif-bold", 54), fill="black", anchor="ma")
    d.text((W // 2, H - 80), "ilsvotentquoi.fr · source : Assemblée nationale", font=fk, fill=(130, 130, 130), anchor="ma")
    img.save(os.path.join(OUT, f"{s['n']}-story.png"), optimize=True)

if __name__ == "__main__":
    only_og = "--only-og" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    todo = sorted(D["scrutins"], key=lambda s: -s["n"])[:limit]
    for i, s in enumerate(todo):
        if not s["g"]: continue
        card_og(s)
        if not only_og: card_story(s)
        if i % 500 == 0: print(f"{i}/{len(todo)}", file=sys.stderr)
    # image par défaut
    img = Image.new("RGB", (1200, 630), "white"); d = ImageDraw.Draw(img); d.rectangle((0, 0, 1200, 8), fill="black")
    d.text((600, 260), "Ils votent quoi ?", font=font("serif-bold", 84), fill="black", anchor="mm")
    d.text((600, 350), "Les votes réels de chaque groupe et de chaque député, sujet par sujet", font=font("sans", 28), fill=(90, 90, 90), anchor="mm")
    d.text((600, 560), "ilsvotentquoi.fr · source : Assemblée nationale", font=font("sans", 22), fill=(130, 130, 130), anchor="mm")
    img.save(os.path.join(ROOT, "dist", "static", "og-default.png"))
