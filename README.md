# Ils votent quoi ? — ilsvotentquoi.fr

Les votes réels de l'Assemblée nationale, scrutin par scrutin, groupe par groupe, député par député.
Sans avis, sans note. Source : open data de l'Assemblée nationale, régénéré chaque nuit.

## Comment ça marche

```
pipeline/run.py     télécharge l'open data (4 zips) → data/site.json        (~2 min)
site/build.py       data/site.json → dist/ (≈10 000 pages HTML statiques)  (~15 s)
site/cards.py       dist/og/<n>.png : une image de partage par vote        (~50 min pour tout, incrémental à venir)
.github/workflows/nightly.yml   fait tout ça chaque nuit et publie sur Cloudflare Pages
```

Aucune dépendance hors bibliothèque standard de Python, sauf Pillow pour les images.

## Lancer en local

```
python3 pipeline/run.py all        # télécharge ~350 Mo puis construit
python3 site/build.py
python3 site/cards.py --limit 50   # 50 cartes pour tester
cd dist && python3 -m http.server 8000
```

## Corriger le classement par sujet

`pipeline/textes_themes.json` : un texte de loi → 1 à 3 sujets (`pipeline/themes.json`).
Les textes que le robot ne connaît pas sont listés dans le résumé de chaque exécution GitHub Actions.
Pour les budgets (`"transversal": true`), chaque amendement est classé par mots-clés (`KW` dans `pipeline/run.py`).

## Secrets à créer dans GitHub (Settings → Secrets → Actions)

- `CLOUDFLARE_API_TOKEN` : jeton Cloudflare avec le droit « Cloudflare Pages : Edit »
- `CLOUDFLARE_ACCOUNT_ID` : visible sur l'aperçu du domaine dans Cloudflare
- `INDEXNOW_KEY` : n'importe quelle chaîne de 32 caractères hexadécimaux ; créer aussi `site/static/<clé>.txt` contenant la clé

## Ce que le site ne fait pas

Il ne dit pas si un vote est une avancée ou un recul. Il ne choisit pas les sujets selon un programme.
Il ne résume pas les textes à la place de leurs auteurs.
