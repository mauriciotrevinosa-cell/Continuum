# The Arrivals — Abandoned Village + Inn Spatial Bible v0.6

**Status:** CREATOR-APPROVED SPATIAL PRODUCTION LOCK  
**Date:** 2026-09-20  
**Project:** `The Arrivals`  
**Branch:** `m3/critical-path`  
**Supersedes:** `THE_ARRIVALS_ABANDONED_VILLAGE_AND_INN_SPATIAL_BIBLE_v0.5.md`

This revision preserves the creator-approved settlement, shell, ground-floor, exterior, and L-shaped stair locks from v0.5. It adds the creator-approved measured second-floor partitions, safe door placements, central corridor, east/west room order, and Frieren north-end terrace relationship approved on 2026-09-20.

For spatial production, v0.6 supersedes older prose, preliminary fit studies, deferred upper-floor-detail notes, and rejected generated interiors wherever they conflict. Generated CAL-02/CAL-03 interiors made before this lock are visual tests only and have no spatial authority. The approved exterior reference remains authoritative for the chimney/terrace architectural relationship.

---

## 1. Core settlement identity

- Small abandoned settlement enclosed by forest.
- The inn is the largest surviving building and the household center.
- Roughly five small abandoned houses surround it irregularly.
- Open ground remains between buildings; the settlement must not read as a dense town.
- Cultivation plot and well sit together on the inn's service side.
- Low hill with one prominent shade tree rises behind the inn.
- Narrow path leads to the lake.
- Former mercantile route is heavily reclaimed by vegetation and initially barely reads as a usable road.
- Lake lies on the sunset side of the settlement and connects to a river/waterway.
- Lake has a small weathered hut and short dock, but no usable boat initially.
- The settlement improves over time while ruined houses may shrink/disappear as salvage is reclaimed.

Visual evolution rule:

> The dead village slowly contracts while the inn becomes more alive.

---

## 2. Coordinate system and orientation

Use the geometric center of the inn as settlement origin:

```text
INN CENTER = (0, 0)
```

Practical orientation:

- East / southeast = main approach and old mercantile route.
- West / southwest = sunset side and lake route.
- North / northwest = service side, cultivation, well, and low hill/tree zone.
- Bedrooms favor stronger morning light.
- Common areas favor warmer late-afternoon/evening light.

The exact world-cardinal bearing may later rotate as a whole, but these relative relationships are canon.

---

## 3. Inn exterior dimensions

Creator-approved dimensional base:

- Main building footprint: **22 m × 13 m**.
- Two principal floors.
- Approximate ground-floor enclosed area: **270–285 m²**.
- Approximate upper-floor enclosed area: **260–280 m²**.
- Ground-floor useful height: **~3.1 m**.
- Upper-floor useful height: **~2.7–2.8 m**.
- Overall roof-ridge height: **~8.5–9 m**.
- Covered exterior porch: **~11 m × 2.4 m**.
- Roof: practical steep rural roof, approximately **42°**, suitable for cold weather / snow.
- Construction language: local stone base / masonry, heavy timber structure, timber-framed upper portions, repairable infill/plaster, broad timber floorboards, weathered shingles or setting-appropriate equivalent.

The inn must remain visibly repairable and imperfect. Later repairs should be legible as repairs rather than making the building visually pristine.

---

## 4. Ground floor — creator-approved measured lock

The clean production drawing is:

`THE_ARRIVALS_INN_GROUND_FLOOR_MEASURED_PRODUCTION_PLAN_v0.2.md`

Its coordinate schedules and opening IDs are binding for CAL-02/CAL-03 spatial production.

### 4.1 Coordinate convention and shell

- Southwest exterior corner = `(0,0)`.
- `+X` runs west → east across the 13 m width.
- `+Y` runs south → north along the 22 m long axis.
- East is the main/porch facade; west is the service facade.
- Exterior shell = **13.00 × 22.00 m = 286.00 m²**.
- Exterior walls = **0.35 m** nominal.
- Clear interior envelope = **12.30 × 21.30 m = 261.99 m²**.
- Normal internal partitions = **0.20 m** nominal.
- Ground-floor useful height remains **~3.1 m**.

### 4.2 Locked measured zones

| Zone | Clear coordinate bounds | Clear dimensions | Clear area |
|---|---|---:|---:|
| Common room | `X 0.35–8.35`, `Y 12.15–21.65` | `8.0 × 9.5 m` | `76.0 m²` |
| Kitchen | `X 0.35–5.35`, `Y 6.00–12.00` | `5.0 × 6.0 m` | `30.0 m²` |
| Wash/service | `X 0.35–4.85`, `Y 1.80–5.80` | `4.5 × 4.0 m` | `18.0 m²` |
| Entry / muddy-boots transition | `X 8.65–12.65`, `Y 12.15–15.15` | `4.0 × 3.0 m` | `12.0 m²` |
| Main stair lower run | `X 11.40–12.65`, `Y 15.35–20.40` | `1.25 × 5.05 m` | `6.31 m²` |
| Main stair northeast turn | `X 11.40–12.65`, `Y 20.40–21.65` | `1.25 × 1.25 m` | `1.56 m²` |
| Main stair upper run | `X 8.00–11.40`, `Y 20.40–21.65` | `3.40 × 1.25 m` | `4.25 m²` |
| Compact upper landing | `X 6.75–8.00`, `Y 20.40–21.65` | `1.25 × 1.25 m` | `1.56 m²` |
| Pantry / dry food storage | `X 5.55–8.55`, `Y 7.15–12.15` | `3.0 × 5.0 m` | `15.0 m²` |
| Flexible work/storage | `X 8.75–12.35`, `Y 7.15–12.15` | `3.6 × 5.0 m` | `18.0 m²` |
| General storage | `X 4.85–10.85`, `Y 1.80–5.80` | `6.0 × 4.0 m` | `24.0 m²` |
| Repair / salvage storage + dry firewood bay | south/east L-shaped bay | — | `~25.0 m²` |
| Utility/service circulation | distributed between the locked zones | minimum `1.20 m` routes | `~26.2 m²` |

The repair/salvage/firewood bay is the union of the south strip `X 0.35–12.65, Y 0.35–1.60` and east leg `X 10.85–12.65, Y 1.80–7.15`, allowing the small partition/gap tolerance shown on the production plan.

### 4.3 Doors, openings, hearth and table

- Main door: east facade, `Y 12.60–14.00`, **1.40 m** clear, opening into the entry transition.
- Entry → common opening: **1.80 m** clear with one raised step.
- Service door: west facade, `Y 10.20–11.25`, **1.05 m** clear, opening from the kitchen/service route toward well and cultivation.
- Common ↔ kitchen: **3.20 m** framed opening; direct visual and social connection is mandatory.
- Kitchen ↔ wash/service: **0.90 m** service door.
- Cellar: **~8 × 6 m** beneath kitchen/service side; access by a **1.20 × 4.0 m** stair at the kitchen's southeast edge.
- Chimney stack: `X 5.00–6.30`, `Y 20.65–21.65`, fixed **1.30 × 1.00 m** footprint in the northwest quadrant.
- Hearth projects south from the chimney stack into the common room.
- Shared table: `X 3.40–4.60`, `Y 14.50–18.10`, **3.60 × 1.20 m**, long axis north–south, with realistic 10–12 person circulation.

### 4.4 Main stair and corrected upper landing — L-shaped production lock

This section supersedes the v0.4 straight-run stair wherever the two conflict. The former low-north/high-south straight run is historical and is not current production geometry.

- Clear stair width remains **1.25 m**, inside the approved 1.2–1.3 m range.
- The lower run occupies `X 11.40–12.65`, `Y 15.35–20.40`, is attached to the **east wall**, begins immediately north of GF-04 entry, and rises **south → north**.
- A usable **0.20 m partition/threshold separation** remains between the north edge of GF-04 (`Y 15.15`) and the first tread (`Y 15.35`); the main door does not open directly onto a tread.
- The 90-degree turn occupies `X 11.40–12.65`, `Y 20.40–21.65` in the **northeast corner**.
- The upper run occupies `X 8.00–11.40`, `Y 20.40–21.65`, is attached to the **north wall**, and rises **east → west**.
- The compact upper landing occupies `X 6.75–8.00`, `Y 20.40–21.65` and opens **west** into the 1.8 m upper corridor.
- The landing and corridor pass **beside** the chimney mass. They may never pass through, overlap, or be drawn inside the chimney.
- The landing delivers naturally toward Frieren's north-end corridor side, while Frieren retains direct ownership and access to the 5 × 1.8 m terrace. The landing may not block or steal that relationship.
- The hearth/chimney and stair remain one directly adjacent architectural cluster. The hearth reaches the landing edge; no room, wall bay, window bay, or passage may be inserted between them.
- The full second floor remains continuous except for the compact L-shaped stairwell opening. There is **no mezzanine and no double-height common room**.

Required measured clarification: E-GF-01 and N-COM-02 retain their exterior positions but become **high stair-light openings**. Their sill/head elevations must be resolved in the later measured-elevation pass so neither opening intersects a tread, landing, or floor structure. No facade opening is relocated by this revision.

### 4.5 Ground-floor opening schedule

| ID | Facade | Position | Width | Serves |
|---|---|---:|---:|---|
| E-GF-01 | East | `Y 16.95–17.90` | `0.95 m` | high lower-stair light; sill/head deferred to elevation pass |
| E-GF-02 | East | `Y 9.00–9.95` | `0.95 m` | flexible work/storage |
| E-GF-03 | East | `Y 4.20–5.15` | `0.95 m` | general/support storage |
| W-K-01 | West | `Y 6.80–7.75` | `0.95 m` | kitchen |
| W-K-02 | West | `Y 8.20–9.15` | `0.95 m` | kitchen |
| W-WASH-01 | West | `Y 3.00–3.65` | `0.65 m` | wash/service |
| N-COM-01 | North | `X 4.20–5.15` | `0.95 m` | common room |
| N-COM-02 | North | `X 10.80–11.65` | `0.85 m` | high upper-stair light; sill/head deferred to elevation pass |
| S-01 | South | `X 3.00–3.95` | `0.95 m` | repair/salvage/firewood bay |
| S-02 | South | `X 9.00–9.95` | `0.95 m` | repair/salvage/firewood bay |

Typical full windows remain approximately 0.85–1.0 m wide × 1.2–1.4 m high. Exact sill and head elevations remain part of the later measured elevation pass.

### 4.6 Locked circulation and area accounting

- Main door → entry → 1.80 m opening → common room.
- Common room → 3.20 m opening → kitchen.
- Kitchen → west service door → well/cultivation side.
- Kitchen → pantry and cellar without crossing the main table zone.
- Common/entry circulation → main stair.
- Normal service routes remain at least **1.20 m** clear.
- Table circulation remains at least approximately **1.4 m** on its tighter occupied-chair sides.

| Accounting item | Area |
|---|---:|
| Gross exterior footprint | `286.0 m²` |
| Exterior-wall footprint | `~24.0 m²` |
| Clear interior envelope | `~262.0 m²` |
| Common + kitchen + wash/service + entry | `136.0 m²` |
| Main stair + upper-landing connection allowance, net of overlap with the common-room envelope | `~11.7 m²` |
| Pantry | `15.0 m²` |
| General storage | `24.0 m²` |
| Repair / salvage storage + dry firewood bay | `~25.0 m²` |
| Flexible work/storage | `18.0 m²` |
| Utility/service circulation | `~26.1 m²` |
| Internal partition allowance | `~6.2 m²` |
| **Total accounted inside exterior walls** | **`~262.0 m²`** |

Rounding may move tenths between circulation and partition allowance without changing locked room dimensions or relationships.

---

## 5. Upper floor — creator-approved order and fit lock

The upper floor remains a complete floor with approximately **262 m²** clear envelope. The room-order intent below is creator-approved and supersedes older generic adjacency wording where it conflicts.

### 5.1 West / primary corridor side, north → south

1. **Frieren**
2. **Bocchi / Fern**
3. **Yuta**
4. **Mau**
5. **Rimuru**

### 5.2 East / opposite side, north → south

1. **Stair / landing zone**
2. **Momo**
3. **Maomao**
4. **Anko**
5. **Flex**

### 5.3 Locked relationships

- Frieren occupies the north chimney/terrace architectural end.
- Frieren's room remains approximately **5.4 × 4.8 m = 25.9 m²**.
- Frieren has direct access from her room to the **5 × 1.8 m** terrace.
- The landing does not separate Frieren from the terrace.
- The **1.8 m** main corridor terminates before Frieren's private north-end block.
- Bocchi/Fern remain immediately beside Frieren and retain approximately **21.6 m²**.
- Yuta and Mau are immediately beside each other in the approved order; Yuta remains approximately **15–16 m²** and Mau approximately **15.1 m²**.
- Mau remains in the same primary corridor cluster as Frieren, but the older generic note that Mau must be directly adjacent to Frieren is superseded.
- Rimuru remains approximately **14–15 m²** at the south end of the west sequence.
- Momo remains approximately **14–15 m²** close to the stair/social side.
- Maomao remains approximately **15–16 m²** immediately south of Momo.
- Anko remains approximately **15–16 m²** toward the quieter part of the floor.
- Flex remains approximately **14 m²** at the south end of the east sequence.
- The chimney stack stays fixed at the north architectural end and may not migrate.
- Full second floor; no mezzanine.

### 5.4 Area-fit confirmation

| Item | Area |
|---|---:|
| Named rooms | `152.1 m²` |
| 1.8 m corridor, approximately 16.3 m run | `~29.3 m²` |
| L-shaped stair void + north-end landing | `~11.7 m²` |
| Chimney stack | `~1.3 m²` |
| Preliminary partition allowance | `~22.0 m²` |
| Closets, vestibules and local fit margin | `~45.6 m²` |
| **Clear upper envelope** | **`~262.0 m²`** |

The external 9.0 m² terrace is excluded from enclosed floor-area accounting. The approved program fits without changing room areas or adding a mezzanine.

### 5.5 Creator-approved measured second-floor production lock

The authoritative measured drawing is:

`THE_ARRIVALS_INN_SECOND_FLOOR_MEASURED_PRODUCTION_PLAN_v0.1.md`

Its coordinate schedule, partitions, stairwell opening, landing, corridor geometry, terrace relationship, and safe door placements are binding for upper-floor production. It supersedes the former deferred-detail note and every rejected upper-floor perspective or preliminary fit study.

The physical lower stair still begins at ground-floor `Y 15.35`. The second-floor opening extends south to `Y 15.00` solely as the creator-approved upper opening/headroom envelope; this does not move the ground-floor entry or its first tread. The chimney datum remains exactly `X 5.00–6.30`, `Y 20.65–21.65` on both floors.

---

## 6. Settlement coordinates — initial E2 base

Coordinates are approximate centers and are intentionally irregular. They are spatial anchors, not a symmetrical village plan.

| Element | Approximate coordinate | Approximate distance from inn |
|---|---:|---:|
| Inn | (0, 0) | — |
| Well | (-13, +7) | ~15 m |
| Initial cultivation plot | (-24, +10) | ~25 m |
| Low hill | (-5, +32) | ~32 m |
| Prominent shade tree | (-3, +40) | ~40 m |
| House 1 | (+22, +18) | ~28 m |
| House 2 | (+30, -6) | ~31 m |
| House 3 | (+13, -28) | ~31 m |
| House 4 | (-20, -25) | ~32 m |
| House 5 | (-32, +2) | ~32 m |
| Lake-path departure | (-18, -12) | ~22 m |
| Mercantile-route approach point | (+45, +4) | ~45 m |

Initial settlement core:
- approximately **90 × 85 m** before forest enclosure becomes substantially denser.

Buildings must not form a decorative circle or evenly spaced ring. Partial visual obstruction by trees, brush, salvage, and terrain is desirable.

---

## 7. Original five houses — creator-approved worker quarters

The five small structures around the inn are primarily former **staff quarters / worker cottages** tied to the inn and its service economy, not five full family houses.

This explains why the inn is comparatively large despite the settlement's tiny scale: the site functioned as a small stopping point on an older mercantile route, with workers living nearby while much of their cooking, bathing, storage, and social life centered on the inn.

The cottages should read as simple rural studio-like dwellings using the same local timber/stone construction language as the inn.

### House 1 — better-preserved staff studio
- approximate area: **28–32 m²**;
- likely suited to one worker, a couple, or a supervisor;
- one main living/sleeping room with simple table, bed, small stove/hearth, storage;
- damaged but meaningfully repairable.

### House 2 — austere two-worker quarter
- approximate area: **24–28 m²**;
- simple sleeping/living arrangement, potentially two beds;
- little or no substantial kitchen because residents could eat/work at the inn;
- useful salvage but structurally more intact than the worst cottages.

### House 3 — service-worker studio
- approximate area: **20–24 m²**;
- likely tied to maintenance, hauling, stable/logistics, or another practical inn function;
- roof partly/substantially collapsed;
- mixed repair/salvage value.

### House 4 — salvage-dominant ruin
- approximate area: **18–22 m²**;
- heavily damaged;
- primarily useful for boards, stone, hardware, frames, doors, and other salvage;
- may visibly shrink/disappear during S1 as the inn is repaired.

### House 5 — recoverable cottage / future-quarter candidate
- approximate area: **25–30 m²**;
- partially damaged but recoverable;
- strongest candidate among the original cottages to become an early independent private quarter outside the inn.

The later S2 residential-quarter idea should evolve naturally from this inherited spatial language rather than introducing modern apartment blocks. The cast does not invent the concept of small residences around the inn from nothing; they restore and extend an arrangement that already existed on the site.

At least some cottages should visibly shrink/disappear as usable materials are reclaimed for the inn and later additions.

---

## 8. Inn exterior identity — creator-approved

The inn must have a repeatable silhouette recognizable across camera angles and repair states.

### 8.1 Primary silhouette

- long rectangular two-storey body, **22 m × 13 m**;
- long axis runs approximately north–south;
- primary facade faces east / southeast toward the entering lane;
- simple steep gable roof, approximately **42°**, ridge running along the long axis;
- second floor projects approximately **0.7–0.8 m** over part of the main facade;
- long covered porch beneath that projection;
- one substantial off-center stone chimney acts as a permanent landmark;
- avoid towers, decorative fantasy-hotel massing, or excessive roof complexity.

The silhouette should still be recognizable as:

> long body + slightly projecting upper floor + steep roof + heavy off-center chimney + long porch.

### 8.2 Main east facade

- covered porch: **~11 × 2.4 m**;
- main door: approximately **1.4 m wide**, heavy timber with visible hardware;
- roughly 2–3 ground-floor windows;
- roughly 5 upper-floor windows;
- openings follow interior room logic and are **not** perfectly symmetrical;
- substantial solid wall sections remain between openings.

### 8.3 Chimney / hearth anchor

- chimney belongs to the northwestern quadrant of the inn and connects to the common-room hearth;
- approximate base: **1.3 × 1.0 m**;
- rises through the building and terminates roughly **1.2–1.5 m above the local roofline**;
- it must not migrate between walls or roof positions from render to render;
- CAL-01 abandoned state has **no smoke**.

### 8.4 West / service facade

- rear/service door: approximately **1.0–1.1 m wide**;
- direct relation to kitchen/service circulation, well, cultivation, salvage area, and lake-path side;
- roughly 2 useful kitchen windows plus a smaller service/wash opening;
- visually more utilitarian than the front facade;
- later-lived states may accumulate firewood, buckets, barrels, tools, temporary work surfaces, and repaired materials here.

### 8.5 Frieren terrace

- approximate size: **5 × 1.8 m**;
- simple timber construction and railing, not ornate;
- attached to / directly serving Frieren's large upper room;
- positioned toward the morning-light side, with an oblique view across part of the settlement;
- the lake remains a separate destination and should not appear immediately below the terrace.

### 8.6 Window continuity

Typical window size:
- approximately **0.85–1.0 m wide × 1.2–1.4 m high**.

Facade opening patterns are stable production anchors:

| Facade | Base opening logic |
|---|---|
| East / main | main entrance + 2–3 ground-floor windows + ~5 upper windows |
| West / service | service door + ~3 ground-floor openings + ~4–5 upper windows |
| North gable | 1–2 useful windows; chimney nearby |
| South gable | ~2 ground-floor + 1–2 upper/terrace-related openings |

Windows may progress visually from broken → boarded → salvaged/repaired glazing → curtains/personalization, but they do not randomly appear or disappear.

### 8.7 Initial E2 structural damage

The abandoned inn is damaged but plausibly repairable.

Required damage language:
- missing shingles on part of the west roof slope;
- one visibly sagging/damaged porch section;
- 2–3 fully broken windows;
- water staining beneath an eave;
- localized missing plaster/infill exposing timber framing;
- damaged porch/floor board;
- fallen or missing gutter/drainage section;
- vegetation pressing against foundation and lower walls;
- at least one damaged service/interior door.

The principal load-bearing structure remains straight and credible. The building should never read as a near-collapse dungeon ruin.

### 8.8 Persistent repair scar

The south end of the roof carries one recognizable old damage / repair scar: a slight irregularity in the eave/roof line that is later structurally repaired but never made visually identical to untouched original construction.

This scar becomes a continuity landmark across the life of the first home.

The building should be able to become warmer, safer, and more personalized without ever losing the physical evidence that the household rebuilt it.

---

## 9. Cultivation and well

### Well
- ~15 m from inn center on service side.
- Close enough for repeated household use.
- Early water is not immediately potable; Rimuru's inspection/repair micro-beat remains valid.

### Initial cultivation
- center approximately 25 m from inn.
- Initial practical plot target: approximately **25 × 35 m**.
- Enough to meaningfully supplement food for roughly ten residents without pretending the household is immediately food-independent.
- May expand and become better organized through S1.

---

## 10. Lake route

The lake should not sit directly beside the inn.

Preferred travel distance:
- approximately **120–180 m** from settlement to lake edge through a narrow wooded path.

This preserves the lake as a nearby but narratively separate place:
- walking conversations;
- private reflection;
- Yuta/Mau scenes;
- Frieren/Mau scenes;
- fishing;
- later route toward waterway/island exploration.

At the lake edge:
- weathered hut;
- short dock;
- no usable boat initially.

---

## 11. Former mercantile route

Historical road width:
- approximately **3.5–4 m**, compatible with carts.

Visible/transitable width at E2:
- often only **~1–1.5 m** because vegetation has reclaimed most of it.

The road approaches from the east / southeast side and becomes more legible only after the cast maps, clears, and reconnects it.

Its gradual recovery is part of the settlement's visual progression.

---

## 12. S1 growth phases

### E2 — RUIN
- inn damaged;
- five abandoned houses;
- broken common infrastructure;
- well unresolved;
- cultivation potential but not organized;
- roads overgrown.

### E8–E9 — HOME
- inn weather-safe enough to inhabit;
- common room, kitchen, storage and rooms increasingly functional;
- terrace / outdoor eating possible;
- cultivation organized;
- well usable;
- dedicated training area;
- music space beginning;
- some nearby houses already losing materials to salvage.

### E12–late S1 — COMPOUND
- bathhouse / hot-bath addition;
- Maomao workroom;
- Anko writing/observation work area;
- Bocchi music area;
- Frieren study/cultivation work;
- practical storage/training areas;
- better internal paths;
- settlement clearly feels lived in rather than merely occupied.

---

## 13. S2 / G3 growth direction

The inn remains the common social heart rather than expanding indefinitely into one giant building.

Growth should increasingly happen around it through:
- workshops;
- bathhouse;
- clinic/workroom;
- storage;
- music/craft spaces;
- small residential quarters;
- repaired original houses where appropriate;
- courtyards and internal paths.

Private residential spaces should feel like small homes / quarters, not modern apartment blocks.

Suggested scale:
- single-person private quarter: **~25–35 m²**;
- pair / mentor-student / small shared quarter: **~40–55 m²**;
- simple private bedroom inside a shared structure: **~15–20 m²**.

Reserve a practical growth band approximately **35–70 m from the inn** so later additions do not destroy the original village geography.

The inn continues to host:
- major meals;
- household councils;
- celebrations;
- arguments;
- arrivals;
- major S2 domestic and political beats.

---

## 14. Fortified late-S2 home

Possible fortified footprint around the matured first settlement:

- approximately **150 × 180 m**;
- area: **~27,000 m² / 2.7 hectares**.

This is a small defended community, not a true city.

The distinction matters:

> first home / fortified settlement ≠ future city.

The later city may occupy tens or hundreds of hectares and should feel like a genuine step change in scale.

---

## 15. Emotional progression of place

The first settlement should physically track the story:

```text
E2 ruin
→ E8 home
→ late-S1 compound
→ early-S2 expanding community
→ G3 residential / functional expansion
→ fortified late-S2 home
→ farewell / relocation
```

The point of growth is not only practical.

By the time the household leaves, they are not abandoning an old inn. They are leaving:
- the common room where they became family;
- the rooms they repaired;
- Bocchi's music space;
- Maomao's work area;
- the bathhouse;
- the cultivation plot;
- the large shared table;
- Frieren and Mau's lived shared room;
- the spaces later arrivals added;
- the first place they consciously called home.

The more functional and personal the settlement becomes, the more emotionally expensive the S2 departure should feel.

---

## 16. CAL-01 production implications

CAL-01 must now treat the settlement as a measurable place.

Minimum spatial anchors:
- inn footprint = 22 × 13 m;
- irregular five-house distribution;
- well ~15 m from inn;
- cultivation centered ~25 m from inn;
- hill ~32 m behind;
- tree ~40 m behind;
- mercantile entry ~45 m from inn center;
- lake path departs southwest/west and continues ~120–180 m to shore;
- open ground between buildings;
- forest enclosure around the ~90 × 85 m original core.

A visually attractive image that changes these anchors is not a successful spatial calibration.

---

## 17. Next spatial pass

The ground-floor measured plan and upper-floor room order are now locked. Later measured work should define:
1. exact upper-floor partitions, door positions and door swings while preserving the locked order;
2. measured elevations and sill/head heights for the locked facade openings;
3. immediate ground surfaces and circulation in the first 10–20 m around the inn;
4. exact path widths, hard/soft surfaces, mud/stone/grass transitions, wood/supply areas, and daily walking routes;
5. exact later bathhouse and outdoor-eating terrace footprints;
6. later G3 residential cluster locations;
7. eventual late-S2 fortified perimeter gates and watch positions.


