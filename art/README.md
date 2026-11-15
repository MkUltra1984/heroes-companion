# Hero artwork

This folder holds small copies of Fire Emblem Heroes artwork for the Heroes Companion fan site. It is kept apart
from the site's code so that it can live in its own repository and be emptied without touching anything else.

## What is in here

| Path | Content |
|---|---|
| `manifest.json` | For every hero: which artwork files exist on the Fire Emblem Heroes Wiki, their original size, the artist's name, and which local copies were made. Written by `tools/fetch_art.py`. |
| `face/{file}.webp` | Square face icon, 128 px. |
| `card/{file}.webp` | Full portrait, 300 px wide. |
| `sprite/{file}_idle.webp`, `sprite/{file}_ok.webp` | Map sprite in two still poses, original size. |

`{file}` is the hero's id with spaces written as underscores, for example `Marth_Altean_Prince`. A Resplendent
attire is stored as `{file}_Resplendent`.

Larger artwork (the full-size portrait and the attack, special and damaged portraits) is not stored here.

## Whose artwork this is

Fire Emblem Heroes, its characters and all artwork in this folder are © Nintendo / INTELLIGENT SYSTEMS. Each
illustration was drawn by the artist named in `manifest.json` (field `artist`), and the site shows that name beside
the artwork.

The files were taken from the Fire Emblem Heroes Wiki (feheroes.fandom.com). The wiki's CC BY-NC-SA licence covers
its text and data, not these images.

## No licence

This is unofficial fan content. Nobody has granted a licence for these images: not to this project and not to
you. They are shown only so that players can recognise the heroes. The project is non-commercial, carries no
advertising, and is not affiliated with or endorsed by Nintendo or Intelligent Systems. Nothing in this folder is
offered for reuse, and the licence of the site's code does not apply to it.

## Removal requests

If you hold rights to any of this artwork, or you are one of the credited artists, and want it removed: open an
issue on this repository's issue page. The artwork will be removed without discussion.
