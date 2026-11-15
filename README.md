# Heroes Companion

A free, fan-made companion web page for Fire Emblem Heroes: every hero with art, level 40 stats, skills and a
data-derived "Standing" description, your own barracks and teams, the running banners compared with what you own
(with rates, verdict and free-pick progress), the quest orbs that are still open, a card per currency and a guide.
Not affiliated with Nintendo or Intelligent Systems. English only. No ads, no tracking, no account.

## Layout

| Path | What |
|---|---|
| `site/` | the page itself, a static single-page app without a build step |
| `site/index.html`, `tokens.css`, `style.css` | shell, design tokens, stylesheet (content security policy in `index.html`) |
| `site/js/` | ES modules: `main`, `router`, `store` (key `hc.v2`), `data`, `time` (game day at 07:00 UTC), `i18n`, `dom`, `shared`, `art`, `motion`, `standing`, `banners`, `carousel`, `content`, `guard` |
| `site/js/pages/` | `home`, `heroes`, `hero`, `summon`, `orbs`, `barracks`, `teams`, `guide` |
| `site/locales/en.json` | every visible text |
| `site/data/` | game data, format version 2, written by `tools/build_data.py` |
| `site/content/` | summon rules, Picks and currency cards, copied from `content/` by `tools/build_site.py` |
| `site/art/`, `site/fonts/` | original interface art (emblem, textures, frames, icons) and the fonts Cinzel and Nunito Sans (SIL OFL 1.1) |
| `content/` | the written content with its sources; edit here, then run `tools/build_site.py` |
| `preview/` | the approved design preview the site's look comes from |
| `art/manifest.json` | checked file names of hero art on the wiki for a sample of heroes (used by tests) |
| `tools/wiki.py`, `tools/fetch_all.py` | read the wiki's data tables politely into `tools/cache/` |
| `tools/build_data.py`, `tools/test_data.py` | turn the cache into `site/data/`, and check it |
| `tools/build_site.py` | copy `content/` into the site and merge the guide texts into the locale file |
| `tools/test_site.py` | static checks, a headless Chrome harness for every page, screenshots |

## Update

```
python -I -B tools/fetch_all.py --fresh     # about an hour: the wiki allows one page of 500 rows per ~40 s
python -I -B tools/build_data.py
python -I -B tools/build_site.py            # after any change in content/
python -I -B tools/test_data.py
python -I -B tools/test_site.py             # add --no-shots to skip the screenshots
```

`-B` keeps Python from writing `__pycache__` folders into the project (compiled files hold absolute paths).

## Look at it locally

```
python -I -B -m http.server 8765 --bind 127.0.0.1 --directory site
```

then open http://127.0.0.1:8765/ . The page must be served over http; opened as a file, modules do not load.

## Data, artwork and licence notes

- Game data comes from the Fire Emblem Heroes Wiki (feheroes.fandom.com); its text and data are licensed
  CC BY-NC-SA. The site names the source on every page; build texts are the wiki authors' words and link to their
  source page. The project is non-commercial.
- Hero artwork (portraits, battle art, map sprites) is © Nintendo / INTELLIGENT SYSTEMS. It is **not stored in
  this repository**: the visitor's browser loads it from the wiki's image host, each hero page credits the
  artist, and a "Show game artwork" switch in the footer turns it off (a designed silhouette shows instead). Rights
  holders can ask for removal on the repository's issue page.
- The interface art in `site/art/` is original and was generated for this project.
- No tier list or rating is copied from other sites. The site shows a description computed from its own data
  ("Standing"), a small hand-written, dated Picks list with sources, and links out to Game8.
- The game offers no account access, so the barracks is filled in by hand and stored in the browser only.
- Paid things (Feh Pass orbs and Feh Pass-only free picks) are labelled and never counted into free totals.
