# Standing block: rules

As of 2026-11-15. For the hero page (block 2) and the "Current" filter of the hero list.

The block describes a hero with facts computed from the site's own data. It is not a rating and must never look like one:
no score, no letter, no stars, no color scale from good to bad, no sorting of heroes by it.

## Text on the page

- Heading: `Standing`
- Line under the heading, always shown: `A description from the game data, not a rating. It does not say how strong this hero is.`
- Link line at the end of the block: `For a rating, see this hero on Game8.`
- The words "tier", "rating", "best" and "meta" appear only in those two lines.

## Fields used

From `site/data/heroes.json`: `r` (release date), `p` (tags), `s` (level 40 stats in the order HP, Atk, Spd, Def, Res),
`bst`, `w` (weapon with color), `m` (movement), `av` (availability), `k` (own skills).
From `site/data/banners.json`: `s`, `e`, `t`, `f` (focus heroes). The data date is `built` in `heroes.json`.

State of the data on 2026-11-15, which the rules must survive:

| Field | State | Consequence |
|---|---|---|
| `k` | empty for all 1,432 heroes | Rule 5 prints its "no data" sentence |
| `f` | empty for all 680 banners | Rule 6 prints its "no data" sentence |
| tag `vista` | removed by the build script | Vista heroes show no type (example 2) |
| tag `aided` | 12 heroes, should be 6 | Rule 3 is right only after the build fix |
| refine and Remix dates | not in the data | Rule 2 uses the `resplendent` tag only |

A rule that has no data prints its "no data" sentence. It never prints "none" or "no".

## Rule 1: age

`months` = whole months from `r` to the data date (count calendar months; subtract one if the day of the month has not
been reached).

| months | Band | Sentence |
|---|---|---|
| 0 to 3 | Current | `Released {date}. One of the newest heroes.` |
| 4 to 9 | Recent | `Released {date}, {months} months ago.` |
| 10 to 18 | Ageing | `Released {date}, {months} months ago. Newer heroes of this kind exist.` |
| 19 and more | Old | `Released {date}, {years} years ago.` with `years` = months / 12 rounded down |

The band word is the first chip of the block. The "Current" filter of the hero list shows band Current only.
`r` empty: chip `Age unknown`, sentence `Release date not in the data.`

Why bands and not a judgement: in the data, the average stat total of melee infantry heroes rises every year
(2017: 158, 2021: 179, 2026: 205), so age is a fact worth showing. It is still only age.

## Rule 2: refreshed

- Tag `resplendent`: sentence `Has a Resplendent outfit: +2 to all stats when you own it (Feh Pass or bought).`
  The outfit is paid, so the sentence is shown in the paid style of decision 9 and does not change the band.
- When the build adds a refine date and a Remix date per hero: if the newest of them is at most 9 months before the
  data date and the band is Ageing or Old, add the chip `Refreshed` after the band chip and the sentence
  `Weapon refined {date}.` or `Skills updated by a Remix {date}.` Until those fields exist, print nothing for them.

## Rule 3: type

Take the tags in this order and print a chip and the sentence for each that is present, at most three:
`emblem`, `legendary`, `mythic`, `chosen`, `vista`, `entwined`, `aided`, `attuned`, `rearmed`, `ascended`, `duo`,
`harmonized`, `brave`, `fallen`, `special`.

| Tag | Chip | Sentence |
|---|---|---|
| emblem | Emblem | `Emblem hero: can engage with one other hero and strengthen that hero.` |
| legendary | Legendary | `Legendary hero: boosts allies with the matching blessing in its season.` |
| mythic | Mythic | `Mythic hero: boosts blessed allies in Aether Raids and changes the Lift you win or lose.` |
| chosen | Chosen | `Chosen hero: grants powers to one hero in Arena, Arena Assault and Allegiance Battles.` |
| vista | Vista | `Vista hero: each copy gives a Vignette (+2 to all stats for another hero).` |
| entwined | Entwined | `Entwined hero: each copy gives a Bouquet (support rank S+ for another hero).` |
| aided | Aided | `Aided hero: each copy gives an Aide's Essence (+1 to all stats for another hero).` |
| attuned | Attuned | `Attuned hero: carries an Echo skill that can be passed on.` |
| rearmed | Rearmed | `Rearmed hero: carries an Arcane weapon and can pass on skills once without being lost.` |
| ascended | Ascended | `Ascended hero: has a second asset. The first copy gives an Ascendant Floret.` |
| duo | Duo | `Duo hero: has a Duo Skill button.` |
| harmonized | Harmonized | `Harmonized hero: has a Harmonized Skill.` |
| brave | Brave | `Brave hero: a winner of the yearly Choose Your Legends vote.` |
| fallen | Fallen | `Fallen hero: an alternate, corrupted version.` |
| special | Seasonal | `Seasonal hero: summoned only on seasonal banners and their re-runs.` |

None of these tags present: no chip, sentence `No special hero type in the data.`
(Not "a regular hero": the data may be missing a tag, as with Vista today.)

The texts for Attuned, Brave and Fallen are from play experience; the others follow the official guide pages listed in
`guide.en.json` and `currencies.json`.

## Rule 4: stats within the class

Class = all heroes in `heroes.json` with the same `m` and the same `w` (the weapon includes its color).
`N` = size of the class, the hero included. `cut` = N / 10 rounded up.

For each of the five stats:
- `higher` = heroes in the class with a strictly higher value; `rank` = higher + 1.
- `lower` = heroes in the class with a strictly lower value.
- `ties` = other heroes in the class with the same value.
- The stat is **high** when `rank` <= `cut`. It is **low** when `lower` < `cut`. With N below 10, `cut` is 1, so only the
  top value and the bottom value count.

Output:
- N below 5: `Only {N} {movement} {weapon} heroes exist, too few to compare.` and nothing else from this rule.
- High stats, in the order HP, Atk, Spd, Def, Res:
  `Among the {N} {movement} {weapon} heroes: {items}.` Each item is
  `highest {Stat} ({value})` when rank is 1 and ties is 0,
  `joint highest {Stat} ({value})` when rank is 1 and ties is above 0,
  `{Stat} {value} (rank {rank})` otherwise.
- Low stats: `Low for this class: {Stat} {value}` joined with commas, ended with a full stop.
- No high stat: `No stat is in the top tenth of the {N} {movement} {weapon} heroes.`
- Stat total, last and smaller: `Stat total {bst}: rank {rank} of {N}. The total matters for Arena scoring, not for strength.`

Stats are level 40, 5 stars, neutral, no weapon, no skills, no merges: say so once in the block's footnote.
A high stat is a fact about numbers. Never add words such as "strong", "good", "excellent" or "weak".

## Rule 5: own weapon and skills

From `k`. A skill counts as personal when the skills data marks it exclusive.

| Case | Sentence |
|---|---|
| `k` empty | `Own weapon and skills: not in the data yet.` |
| personal weapon, n other personal skills (n >= 1) | `Has a personal weapon and {n} more personal skill(s): {names}.` |
| personal weapon only | `Has a personal weapon: {name}. Its other skills can be learned by other heroes.` |
| no personal skill | `All of this hero's skills can be learned by other heroes.` |

Chip when at least one is personal: `{count} personal skills` (count includes the weapon).

## Rule 6: banner history

From `f` of all banners, over the span the banner data covers (first `s` to last `s`, today 2024-08-16 to 2026-11-15).

| Case | Sentence |
|---|---|
| every `f` in the data is empty | `Banner history: not in the data yet.` |
| on a banner that runs today | `On a banner now: {name}, ends {date and hour}.` |
| past banners only | `On {n} banner(s) since {first date of the data}. Last: {name}, ended {date}.` |
| focus data exists, hero on none | `On no banner since {first date of the data}.` |

For tags `legendary` and `mythic` add `Legendary and Mythic heroes usually return about every three months.`
(official guide).

## Rule 7: how to get

From `av` and tags, first match wins:

| Condition | Chip | Sentence |
|---|---|---|
| `av` = "Heroic Grails" | Heroic Grails | `Free to get: bought with Heroic Grails.` |
| tag `story` | Free | `Free: joins during the story.` |
| `av` = "3-4 star summoning pool" | 3 to 4-star pool | `In the normal pool at 3 and 4 stars: appears on every banner that has those rarities.` |
| `av` = "4-star special rate" | 4-star special rate | `Appears as a 4-star special rate hero (3% on most banners), not as a regular 5-star.` |
| `av` empty | none | `Summoned at 5 stars. See the banner history for where.` |

## Rule 8: refresher

Tag `refresher`: chip `Refresher`, sentence `Can give another hero a second action (Sing, Dance or Play).`
This is the only role the tags give. Other roles need skill texts (`k`) and are specified in `hero_notes.md`.

## Layout

1. Chips in one line: band, `Refreshed` if any, type chips (at most three), `Refresher` if any, the how-to-get chip.
2. Sentences in the order of rules 1, 2, 3, 8, 4, 5, 6, 7.
3. Footnote and the Game8 link line.

## Worked examples (data of 2026-11-15)

### 1. Hector: Of Strength (`Hector Of Strength`)

Data: `r` 2026-10-30, tags `emblem`, Armored, Green Axe, stats 55/50/16/50/46, total 217, `av` empty.
Class: 34 armored green axe heroes, cut 4. HP rank 2; Atk rank 1 with 3 ties; Spd 0 heroes lower; Def rank 1 with
1 tie; Res rank 2. Total rank 1.

Chips: `Current` `Emblem`

- Released 30 Oct 2026. One of the newest heroes.
- Emblem hero: can engage with one other hero and strengthen that hero.
- Among the 34 armored green axe heroes: HP 55 (rank 2), joint highest Atk (50), joint highest Def (50), Res 46 (rank 2).
- Low for this class: Spd 16.
- Stat total 217: rank 1 of 34. The total matters for Arena scoring, not for strength.
- Own weapon and skills: not in the data yet.
- Banner history: not in the data yet.
- Summoned at 5 stars. See the banner history for where.

### 2. Gullveig: Seer Reborn (`Gullveig Seer Reborn`)

Data: `r` 2026-10-16, no tags, Cavalry, Colorless Tome, stats 40/47/49/33/21, total 190, `av` empty.
Class: 8 cavalry colorless tome heroes, cut 1. Spd rank 1 with 1 tie; Def rank 1, no tie; Atk rank 2; Res has 2
heroes lower, so it is not low.

Chips: `Current`

- Released 16 Oct 2026. One of the newest heroes.
- No special hero type in the data.
- Among the 8 cavalry colorless tome heroes: joint highest Spd (49), highest Def (33).
- Stat total 190: rank 1 of 8. The total matters for Arena scoring, not for strength.
- Own weapon and skills: not in the data yet.
- Banner history: not in the data yet.
- Summoned at 5 stars. See the banner history for where.

This hero is a Vista hero in the game. The build script removes the tag, so the block cannot say so. Once the tag is
kept, the chip `Vista` and its sentence appear with no change to these rules.

### 3. Byleth: Of the Academy (`Byleth Of the Academy`)

Data: `r` 2026-01-29, tags `emblem`, `refresher`, Infantry, Blue Tome, stats 40/46/49/41/17, total 193.
Months: 9 (29 Jan to 15 Nov). Class: 49 infantry blue tome heroes, cut 5. Atk rank 4; Spd rank 1; Def rank 1;
Res 0 heroes lower; HP rank 9, not high.

Chips: `Recent` `Emblem` `Refresher`

- Released 29 Jan 2026, 9 months ago.
- Emblem hero: can engage with one other hero and strengthen that hero.
- Can give another hero a second action (Sing, Dance or Play).
- Among the 49 infantry blue tome heroes: Atk 46 (rank 4), highest Spd (49), highest Def (41).
- Low for this class: Res 17.
- Stat total 193: rank 1 of 49. The total matters for Arena scoring, not for strength.
- Own weapon and skills: not in the data yet.
- Banner history: not in the data yet.
- Summoned at 5 stars. See the banner history for where.

### 4. Black Knight: Sinister General (`Black Knight Sinister General`)

Data: `r` 2017-09-23, tags `tempest`, `limited`, `resplendent`, `muspell`, Armored, Red Sword, stats 48/34/34/35/18,
total 169, `av` "Heroic Grails". Months: 109, so 9 years. Class: 16 armored red sword heroes, cut 2. No stat has
rank 1 or 2. Atk, Def and Res each have 1 hero lower, so all three are low.

Chips: `Old` `Heroic Grails`

- Released 23 Sep 2017, 9 years ago.
- Has a Resplendent outfit: +2 to all stats when you own it (Feh Pass or bought).
- No special hero type in the data.
- No stat is in the top tenth of the 16 armored red sword heroes.
- Low for this class: Atk 34, Def 35, Res 18.
- Stat total 169: rank 13 of 16. The total matters for Arena scoring, not for strength.
- Own weapon and skills: not in the data yet.
- Banner history: not in the data yet.
- Free to get: bought with Heroic Grails.

### 5. Abel: The Panther (`Abel The Panther`)

Data: `r` 2017-02-02, no tags, Cavalry, Blue Lance, stats 39/33/32/25/25, total 154, `av` "3-4 star summoning pool".
Months: 117, so 9 years. Class: 64 cavalry blue lance heroes, cut 7. Best rank is Res at 20. Def has 3 heroes lower,
so it is low; HP has 7 lower, so it is not.

Chips: `Old` `3 to 4-star pool`

- Released 2 Feb 2017, 9 years ago.
- No special hero type in the data.
- No stat is in the top tenth of the 64 cavalry blue lance heroes.
- Low for this class: Def 25.
- Stat total 154: rank 55 of 64. The total matters for Arena scoring, not for strength.
- Own weapon and skills: not in the data yet.
- Banner history: not in the data yet.
- In the normal pool at 3 and 4 stars: appears on every banner that has those rarities.

## Checks for the build

- Hector: Of Strength gives exactly the chips and sentences of example 1.
- No output of this block contains a digit followed by "/10", a letter grade, or the words listed under "Text on the page".
- With `k` and `f` empty, no hero page prints "no personal skills" or "on no banner".
