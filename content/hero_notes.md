# Hero page: written sections

As of 2026-11-15. Templates for the three hero page sections that are text, not computed numbers: the role line,
"How to get", and "How to build". `{...}` are values from the data. Each template names the data it needs; when that
data is missing, the "no data" line is shown instead. Nothing is filled with a guess (plan decision 10).

Spelling follows the locale file (US: color, armored).

## 1. Role line

One line under the hero's name. It says what the hero does on the map, built from the hero's own skills.

### 1.1 Role chips

Needs the own skills in `k` with their texts. Test in this order, show every chip that matches, at most three.

| Chip | Condition on the hero's own skills |
|---|---|
| Refresher | tag `refresher`, or an Assist named Sing, Dance or Play (also as part of a longer name) |
| Healer | weapon class Staff |
| Save tank | a skill whose name contains "Save" and whose text contains "Savior" |
| Extra action | a skill text contains "grants another action" or the Special is Galeforce |
| Hit and run | a skill text contains "Canto" |
| Mobility support | a skill text contains "Pathfinder", or a skill name contains "Guidance" or "Orders", or the text lets allies "move to a space adjacent" (warp) |
| Counters at any range | a skill text contains "can counterattack regardless of" |
| Ranged attacker | weapon class Tome, Bow, Dagger, or Staff with none of the chips above |
| Melee attacker | every other hero with none of the chips above |

The keyword list is a first version. Before release, run it over all heroes and read the result for the 30 newest:
a chip that is wrong on one of them is removed from the table, not patched by hand.

### 1.2 The line

| Case | Template |
|---|---|
| chips found | `{Movement} {weapon class} hero. {Chip 1}, {chip 2}, {chip 3}.` |
| `k` empty | `{Movement} {weapon class} hero. Role: skill data not loaded yet.` |

Examples: `Armored axe hero. Save tank.` / `Infantry tome hero. Refresher.` /
`Cavalry lance hero. Role: skill data not loaded yet.`

### 1.3 "Why" sentence

Only for heroes in `content/picks.json`: show the pick's `why` text under the role line, followed by
`From the picks of {month} {year}.` No other hero gets a written sentence. The page does not invent one from stats.

## 2. How to get

Needs `av`, the tags, and the banners' focus lists `f`. Show the first matching "now" line, then the "usual way" line.

### 2.1 Now

| Case | Template |
|---|---|
| focus hero on a running banner | `On a banner now: {banner name}. Ends {weekday} {date}, {hour}. {verdict text of the banner type from summon_rules.json}` |
| on several running banners | one line per banner, the one that ends first on top |
| no running banner, focus data exists | `Not on a banner today.` |
| focus data missing (all `f` empty) | `Which banners feature this hero: not in the data yet. Check the Summon page or the game.` |

The end is local date and hour, computed from the UTC end time. If the banner type's free pick is `everyone`, add
`Free pick after 40 summons.` If it is `feh_pass`, add `Free pick after 40 summons with Feh Pass only.` and only when
the Feh Pass setting is on count it as reachable. If it is `not_listed` or null, add nothing.

### 2.2 The usual way

First match wins.

| Condition | Template |
|---|---|
| `av` = "Heroic Grails" | `Free: buy copies with Heroic Grails (Allies, Use Heroic Grails). The price rises with each copy of the same hero.` |
| tag `story` | `Free: joins your army during the story.` |
| `av` = "3-4 star summoning pool" | `In the normal pool at 3 and 4 stars. You will meet this hero while summoning for others; do not summon for it.` |
| `av` = "4-star special rate" | `Appears as a 4-star special rate hero: a 3% chance per summon on most banners, shared among all heroes of that group.` |
| tag `legendary` or `mythic` | `Only on Legendary and Mythic banners (8% focus, twelve heroes). These heroes usually return about every three months, and later on Remix and revival banners.` |
| tag `emblem` | `Only on Emblem banners (8% focus, twelve heroes), and later on Remix banners.` |
| tag `special` | `Only on seasonal banners: its own, the re-run a year later, and Double Special Heroes banners.` |
| none of these, `av` empty | `Summoned at 5 stars: on its own New Heroes banner, then on New Heroes Return and revival banners.` |

After the line, when focus data exists: `Last banners: {name} ({month year}), {name} ({month year}), {name} ({month year}).`
with the three most recent. When the hero was on none: `On no banner since {first date of the banner data}.`

Texts in this table that name a banner path ("later on Remix", "the re-run a year later") describe the usual pattern
seen in the banner data of 2024 to 2026. They are not a promise of a date, and no date is ever printed from them.

## 3. How to build

Plan decision 3: the hero's own kit is the default build. Wiki builds are shown openly only when recent.

### 3.1 Default: the kit as summoned

Needs `k`. Show the own skills in the build layout (weapon, Assist, Special, A, B, C, X), the highest version of each.

Heading: `Build: as summoned`

| Case | Text under the heading |
|---|---|
| released 2024-01-01 or later, every slot A, B, C filled, personal weapon | `This hero comes complete. Use its own skills and add a Sacred Seal.` |
| released 2024-01-01 or later, a slot empty | `Use its own skills. Empty: {slot names}. Fill them with a skill another hero can pass on, and add a Sacred Seal.` |
| released before 2024, weapon can be refined (when refine data exists) | `Start with its own skills and refine the weapon in the Weapon Refinery. Skills from before 2024 are usually worth replacing; see the older builds below for ideas.` |
| released before 2024, otherwise | `Its own skills are from {year}. They work in story maps; for harder modes this hero needs newer skills passed on from other heroes.` |
| `k` empty | `Own skills: not loaded yet. See the wiki page for this hero's skills.` |

Always add, as its own small line: `Sacred Seal: not part of a hero. Pick one from the seals you own.`
The page does not name a seal: no dated source for seal choices was collected.

The words "comes complete" are used only under the first condition. They mean every slot is filled with the hero's own
skills; they do not mean the hero is strong.

### 3.2 Wiki builds, shown openly

A wiki build is shown below the kit, without a fold, only when one of these holds:
- the hero's release date is 2024-01-01 or later, or
- the build row carries a date of 2024-01-01 or later.

Heading: `Community build from the wiki`
Line under each build: `{build name}. From the Fire Emblem Heroes Wiki, {date or "undated"}. Open on the wiki.`
(link to the hero's build page; licence note per plan decision 5).

### 3.3 Older wiki builds, folded

Every other build goes into a closed fold.

Fold label: `Old community builds ({n})`
First line inside the fold: `These builds were written in {year or "an unknown year"}. Skills and heroes released since then are missing, so use them for ideas, not as a recommendation.`

An undated build of a hero released before 2024 is always treated as old.

### 3.4 No build at all

| Case | Text |
|---|---|
| kit shown, no wiki build | nothing more: the kit is the build |
| `k` empty, no wiki build | `No build data for this hero yet.` plus the links to the wiki page and to Game8 |

The old text `The wiki has no build for this hero in its data.` is removed. For a hero of 2024 or later the missing
wiki build is normal and needs no apology.

### 3.5 Build text rules

- Never cut a description in the middle of a word or sentence. If it is too long, show the first whole sentences up
  to the limit and a `Show all` control.
- Strip wiki markup before display: `[[link|text]]` becomes `text`, `{{...}}` templates and `<...>` tags are removed.
  A text that still contains `[[`, `{{` or `<` after cleaning is not shown; the link to the wiki is shown instead.
- Build type, mode and cost are shown only when they match the fixed lists (`optimal`, `alternative`, `creative`,
  `budget`; `general`, `arena`, `ar-offense`, `ar-defense`, `chain`; `low`, `medium`, `high`, `very high`). Any other
  value is left out, not printed raw.

## 4. Type chips: tap text

One line per chip, shown on tap. The same sentences as rule 3 of `standing_rules.md`; keep one copy of them in the
locale file under `tagdesc.<tag>` and use it in both places. `tag.vista` and `tagdesc.vista` must be added.

## Sources for the fixed texts

- Banner types, rates and free pick: `content/summon_rules.json`.
- Heroic Grail price ladder: Fire Emblem Heroes Wiki, Use Heroic Grails, revision of 2026-11-05.
- Legendary and Mythic heroes return about every three months: official guide,
  https://new-guide.fire-emblem-heroes.com/en-GB/feh-3120.html (undated, read 2026-11-15).
- Wiki build coverage by year (203 of 203 heroes of 2017, 5 of 100 heroes of 2026): review round 1, measured on
  `tools/cache/HeroBuilds.json`.
- The role keywords and the build advice for heroes from before 2024 are the author's experience as a player and
  must be checked on real pages before release.
