#!/usr/bin/env python3
"""
ilsvotentquoi.fr — reels (vidéos verticales 1080×1920, ~11 s) pour chaque vote décisif.

    python site/reels.py                 # tous les votes décisifs (ensemble d'un texte, motions) sans reel déjà présent
    python site/reels.py --only 8434     # un seul, pour tester
    python site/reels.py --limit 5

Sortie : dist/reels/<n>.mp4 (H.264, son muet ; la musique s'ajoute dans Instagram).
La page est animée en CSS/JS, enregistrée par Playwright (webm) puis convertie par ffmpeg.
Même règle que les cartes : aucun choix éditorial, un reel par vote décisif, le texte dit ce que le vote est.
"""
import json, os, shutil, subprocess, sys, tempfile, concurrent.futures
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards as C

ROOT = C.ROOT; OUT = os.path.join(ROOT, "dist", "reels"); os.makedirs(OUT, exist_ok=True)
D, COL, ORDER = C.D, C.COL, C.ORDER
esc = C.esc

CSS = C.CSS + """
html,body{width:1080px;height:1920px}
.card{padding:110px 72px 90px}
.q{font-size:52px;margin-top:30px;opacity:0;transform:translateY(20px);animation:up .5s .3s forwards}
h1{font-size:76px;line-height:1.02;margin-top:14px;opacity:0;transform:translateY(20px);animation:up .6s .7s forwards}
h1.long{font-size:58px}
.sub{font-size:30px;opacity:0;animation:up .5s 1.2s forwards}
.hemi{margin:auto 0;width:100%}
.hemi circle{opacity:0;transform-origin:center;animation:pop .25s forwards}
.res{opacity:0;transform:translateY(16px);animation:up .5s 6.2s forwards}
.pill{font-size:34px;padding:18px 38px}
.tally{font-size:42px}
.positions{gap:14px;margin-top:40px;opacity:0;animation:up .5s 7s forwards}
.pos{font-size:32px}.pl{font-size:24px;width:220px}
.chip{font-size:28px;padding:8px 18px 8px 12px}.chip i{width:16px;height:16px}
.tex{font-size:24px;opacity:0;animation:up .4s 7.6s forwards}
.brand{opacity:0;animation:up .5s 8s forwards}
.brand b{font-size:46px}.brand span{font-size:24px}
.kicker{font-size:24px;opacity:0;animation:up .4s .1s forwards}
.bar-progress{position:absolute;left:0;top:0;height:12px;background:#B91D47;width:0;animation:grow 11s linear forwards}
@keyframes up{to{opacity:1;transform:none}}
@keyframes pop{0%{opacity:0;transform:scale(.2)}70%{opacity:1;transform:scale(1.25)}100%{opacity:1;transform:scale(1)}}
@keyframes grow{to{width:100%}}
"""

def hemi_svg_animated(s):
    """Comme cards.hemi_svg mais chaque point apparaît à son tour, groupe par groupe (gauche → droite), en ~4 s."""
    ppl = C.people(s)[:577]; n = max(1, len(ppl)); dots = []
    for k, (g, vote, _) in enumerate(ppl):
        x, y, _ = C.SEATS[k]; c = COL[g]; delay = 1.6 + 4.0 * k / n
        st = f'style="animation-delay:{delay:.2f}s"'
        xs, ys = f"{x:.1f}", f"{y:.1f}"
        if vote == "P": dots.append(f'<circle {st} cx="{xs}" cy="{ys}" r="6.4" fill="{c}"/>')
        elif vote == "C": dots.append(f'<g {st} class="d"><circle cx="{xs}" cy="{ys}" r="6.4" fill="{c}"/><path d="M{x-2.7:.1f} {y-2.7:.1f}l5.4 5.4M{x+2.7:.1f} {y-2.7:.1f}l-5.4 5.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></g>')
        elif vote == "A": dots.append(f'<circle {st} cx="{xs}" cy="{ys}" r="6.4" fill="url(#h-{g})"/>')
        else: dots.append(f'<circle {st} cx="{xs}" cy="{ys}" r="6.4" fill="#fff" stroke="{c}" stroke-width="1.3"/>')
    defs = "".join(f'<pattern id="h-{g}" patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)"><rect width="4" height="4" fill="{COL[g]}"/><rect width="2" height="4" fill="#fff" opacity=".75"/></pattern>' for g in ORDER)
    return f'<svg viewBox="0 0 600 300" xmlns="http://www.w3.org/2000/svg"><defs>{defs}</defs>{"".join(dots)}</svg>'

def reel_html(s):
    q, t1, tx = C.headline(s); ok = s["s"] == 1
    res = f'<div class="res"><span class="pill {"" if ok else "no"}">{"Adopté" if ok else "Rejeté"}</span><span class="tally"><b>{s["t"][0]}</b> pour<span>·</span><b>{s["t"][1]}</b> contre<span>·</span><b>{s["t"][2]}</b> abst.</span></div>'
    body = (f'<div class="card"><div class="bar-progress"></div><p class="kicker"><b>Assemblée nationale</b> · {C.fdate(s["d"])} · scrutin nº {s["n"]}</p>'
            f'<p class="q">{esc(q)}</p><h1 class="{"long" if len(t1) > 90 else ""}">{esc(t1)}</h1>{f"<p class=sub>{esc(tx)}</p>" if tx else ""}'
            f'<div class="hemi">{hemi_svg_animated(s)}</div>{res}{C.positions(s)}'
            f'<p class="tex">● pour &nbsp; ⊗ contre &nbsp; ▨ abstention &nbsp; ○ absent &nbsp;·&nbsp; couleur = groupe</p>'
            f'<div class="brand"><b>Ils votent <em>quoi</em> ?</b><span>ilsvotentquoi.fr · source : Assemblée nationale</span></div></div>')
    extra = "<style>.hemi g.d{opacity:0;animation:pop .25s forwards}.hemi g.d circle{opacity:1;animation:none}</style>"
    return f'<!doctype html><html lang="fr" class="story"><head><meta charset="utf-8">{C.FONTS}<style>{CSS}</style>{extra}</head><body>{body}</body></html>'

DURATION = 11.0

def record(s, tmpdir):
    from playwright.sync_api import sync_playwright
    dst = os.path.join(OUT, f"{s['n']}.mp4")
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1080, "height": 1920}, record_video_dir=tmpdir, record_video_size={"width": 1080, "height": 1920})
        pg = ctx.new_page(); pg.set_content(reel_html(s), wait_until="load"); pg.wait_for_timeout(int(DURATION * 1000))
        path = pg.video.path(); ctx.close(); b.close()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-t", str(DURATION), "-vf", "fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", dst], check=True)
    os.remove(path); return dst

def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    todo = [s for s in sorted(D["scrutins"], key=lambda s: -s["n"]) if s["k"] in ("e", "m") and s["g"]]
    if only: todo = [s for s in todo if str(s["n"]) == only]
    todo = [s for s in todo if only or not os.path.exists(os.path.join(OUT, f"{s['n']}.mp4"))][:limit]
    print(f"reels à produire : {len(todo)}", file=sys.stderr, flush=True)
    tmp = tempfile.mkdtemp()
    with concurrent.futures.ThreadPoolExecutor(int(os.environ.get("IVQ_REEL_WORKERS", "4"))) as ex:
        for i, dst in enumerate(ex.map(lambda s: record(s, tmp), todo)):
            if i % 20 == 0: print(f"{i}/{len(todo)} {os.path.basename(dst)}", file=sys.stderr, flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    json.dump(sorted(int(f[:-4]) for f in os.listdir(OUT) if f.endswith(".mp4")), open(os.path.join(ROOT, "dist", "api", "reels.json"), "w"))

if __name__ == "__main__": main()
