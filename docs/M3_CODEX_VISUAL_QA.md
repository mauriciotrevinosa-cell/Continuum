# M3 continuation — visual QA and creator handoff

Date: 2026-09-15. Branch: `m3/critical-path`.
Fetched and verified starting HEAD and origin: `416e03aae08969b516c7d99c67b9c91d07c3b7f7`.
Resulting engineering HEAD: the commit containing this report (`git log -1`).

## Outcome and stop condition

**STOP B: creator review required. Page 3 is NOT yet ready for a real GPU render.**
No sample decision, no canonical run, no page approval, no story rewrite and no production render were performed.
The normal sample still has continuity v3 and page 3 READY, with zero attempts on page 3. READY is a workflow state, not a claim of visual readiness.

## Engineering changes

Grammar ranking applies a 0.35 penalty per use in the preceding two planned pages; technique uses 0.18. Only a bounded recent window influences scores. Grammar still requires positive underlying relevance and retains source-series diversity. A strongly superior reference or a limited pool can repeat. No random shuffling, schema migration or persistent index.

Chapter history is replayed deterministically within the same run and materialized chapter, without recursive full bundle assembly. Direct page viewing, chapter viewing and arbitrary viewing order select the same references. Existing attempts and approved diagrams remain immutable; fresh bundles change, historical renders are not regenerated.

Tests cover relevant alternatives, repeatability after reversed candidate order, a strong repeat beating weak alternatives, zero relevance, scarce technique pools and actual direct/chapter integration. Complexity is a linear replay for a direct page; chapter review repeats the replay per page. This is deliberately small; a persistent index was not added.

The API was reloaded on port 8002, preserving the worker and database. Browser inspection verified the existing chapter UI on port 3001. The old `.env.local` port 8010 is not the launched app; `.claude/launch.json` specifies 8002.

## Measured chapter results

| Metric | Before | After |
|---|---:|---:|
| Technical diagrams present | 16 | 16 |
| Pages with grammar | 16 | 16 |
| Repeated grammar sets | 4 | 1 |
| Possible repeated compositions | 2 | 1 |
| Automated environment gaps | 7 | 7 |
| Pages carrying unconfirmed Frieren candidates | 14 | 14 |

Before: several craft locators appeared on 9–16 pages. After: only one craft locator remains above the chapter threshold (9 pages); the two identity candidates still recur on 14. This improves variety, **not semantic verification**. The remaining repetition is allowed rather than forcing irrelevant pages into the bundle.

## Visual findings the automated summary missed

Reviewed all 16 scripts/plans, all 16 TEST images, every unique baseline selected source/reference image, and a small early-chapter source shortlist (63 image entries total). TEST images are blank technical canvases with input thumbnails/footer, not artwork. They cannot establish pose, costume, lighting or compositional continuity.

1. **Invalid body anchor:** `01a0a2c1-916a-7427-80f1-c548b1fdea00`, “Frieren full figure, opening chapter”, serves a **table of contents** with a tiny decorative silhouette. It cannot establish body proportions. Its inherited CONFIRMED label is not visual proof. Review/reject this association and replace it with Ch3 p24 below. No creator confirmation was impersonated or changed in this pass.
2. **Wrong identity candidates:** Ch91 p14 (`01a0a2c1-91c7-72b9-9561-dc7647139aaa`) shows other figures, including a horned figure, and Ch123 p13 (`01a0a2c1-91c7-72f9-8980-85537c1ba025`) shows a dark-haired human girl with a young man. Neither inspected page verifies Frieren. Reject the Frieren association; the pages may remain useful in other roles. Ch123 should be reviewed for Fern instead, not automatically confirmed.
3. **Role mismatch:** Kagurabachi Ch0 p94 is violent action with heavy narrative blacks, not a strong restrained-expression lesson. Jujutsu Kaisen Ch0 p94 is an impact/combat layout, not quiet interpersonal silence. These pages are valid source material but poorly suited to Page 3's technique needs.
4. **Layout-only traps:** Witch Hat Atelier Ch0 p11 is a small partial colored strip in the served image; Solo Leveling Ch0 p37 is essentially a black field with “BEEP”. Neither proves flower effects or a useful full manga layout. Do not upgrade layout hints to content verification.
5. **Environment mismatch:** Frieren Ch72 p10 and Ch84 p10 show interior/architectural scenes. Their large panels do not establish forest, trail or flower field.
6. **Acting contamination:** page-level confusion is applied to both character retrieval needs, even where only Mau is disoriented. Preserve Frieren's attentive/deadpan acting in the visual pack. No automatic narrative rewrite was made.
7. **Wardrobe:** Mau Anime V2 is PROJECT_CREATED / STYLIZATION, not primary identity. The creator rejected its clothing. No E1 costume can be frozen from that sheet or modern creator photos.

The page-by-page visual review below describes the **baseline handoff bundle**; automated after-change metrics are above. Newly varied references remain layout candidates until visually curated. No blanket visual PASS is claimed.

## Page-by-page QA

Global continuity for the preview: WORKFLOW_TEST, no approved continuity. The separate sample's approved pages 1–2 are TEST_RENDER only and must not condition character identity as artwork.

### PAGE 1 — NEEDS ATTENTION (integrated p42)

- CAST: Frieren, Mau; primary Mau; supporting Frieren. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Cautious approach and unconscious Mau need eye-line and reclining pose support. Current photos show standing poses; do not infer sleeping anatomy from them.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE.

### PAGE 2 — NEEDS ATTENTION (integrated p43)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Blurred Mau POV must resolve onto Frieren, not a generic front portrait. Preserve the prior ground position; no established rendered pose exists.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; REPEATED_GRAMMAR.

### PAGE 3 — NEEDS ATTENTION (integrated p44)

- CAST: Frieren, Mau; primary Mau; supporting Frieren. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Keep Frieren calmly attentive and Mau disoriented. Page-wide confused tagging currently affects both retrieval needs. Use the compact pack; hold a clear pause between the question and the name.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; REPEATED_GRAMMAR.

### PAGE 4 — NEEDS ATTENTION (integrated p45)

- CAST: Frieren, Mau; primary Mau; supporting Frieren. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Mau searches memory rather than reacting comically. Avoid repeating page 3 geometry merely because the intents match.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; REPEATED_GRAMMAR; POSSIBLE_REPEATED_COMPOSITION.

### PAGE 5 — NEEDS ATTENTION (integrated p46)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: the-ramparts-of-ice / Chapter 1 p8; the-fragant-flower-blooms-with-dignity / Chapter 0 p97; kagurabachi / Chapter 0 p94. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: frieren-beyond-journey-s-end / Chapter 1 p20. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Three dialogue lines need RTL balloon order and a restrained head shake. The source Ch1 p20 conversational staging is useful; full-body index remains invalid.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE.

### PAGE 6 — NEEDS ATTENTION (integrated p47)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Mau has emotional focus although the lexical primary is Frieren. Her stopping the questioning should read through a pause, not a second confused face.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE.

### PAGE 7 — NEEDS ATTENTION (integrated p48)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; am-i-actually-the-strongest / Chapter 0 p6; jujutsu-kaisen / Chapter 0 p94; the-angel-next-door-spoils-me-rotten / Chapter 0 p3; rich-girl-caretaker / Chapter 1 p17; frieren-beyond-journey-s-end / Chapter 1 p20. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; you-and-i-are-polar-opposites / Chapter 1 p24; my-deer-friend-nokotan / Chapter 1 p14. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; only unverified wide source pages.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: A wide two-character pause needs actual body/back or seated pose evidence and a grounded forest plane. The suggested source Ch72/84 interiors do not establish this outdoor space.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; ENVIRONMENT_GAP.

### PAGE 8 — NEEDS ATTENTION (integrated p49)

- CAST: Mau; primary Mau; supporting none. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator face/body grounding and V2 stylization available; photo poses and costume do not establish this scene.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: you-and-i-are-polar-opposites / Chapter 1 p24; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Mau-only framing is consistent with the written page; do not automatically add Frieren. Internal noise is not spoken dialogue. Cartoon alarm/wakeup examples exaggerate the intended disturbance.
- BASELINE WARNINGS: none automatically; visual gaps remain.

### PAGE 9 — NEEDS ATTENTION (integrated p50)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: the-ramparts-of-ice / Chapter 1 p8; the-fragant-flower-blooms-with-dignity / Chapter 0 p97; kagurabachi / Chapter 0 p94. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: frieren-beyond-journey-s-end / Chapter 1 p20. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Four lines require clean speaker alternation and eye-lines. Frieren is asking about what Mau heard; do not imply that she heard it too.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE.

### PAGE 10 — NEEDS ATTENTION (integrated p51)

- CAST: Frieren, Mau; primary Mau; supporting Frieren. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: No automatic warning, but no tagged outdoor support; the continuing scene still needs a consistent forest plane.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: Mau looks to an absent source while Frieren watches. Distinguish two acting needs; the page-wide confused tag is not evidence of her confusion.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE.

### PAGE 11 — NEEDS ATTENTION (integrated p52)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; jujutsu-kaisen / Chapter 0 p94. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; only unverified wide source pages.
- CONTINUITY: technical diagram only; pose, eye-lines, scale and light are not established by TEST approvals.
- NOTES: The scene title mentions flowers before the spell begins. Do not pre-fill the flower field from a tag: this is the before-state. Maintain forest continuity.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; ENVIRONMENT_GAP; REPEATED_GRAMMAR; POSSIBLE_REPEATED_COMPOSITION.

### PAGE 12 — NEEDS ATTENTION (integrated p53)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: solo-leveling / Chapter 0 p37; tokyo-ghoul / Chapter 0 p18; jujutsu-kaisen / Chapter 0 p94; am-i-actually-the-strongest / Chapter 0 p6; the-angel-next-door-spoils-me-rotten / Chapter 0 p3; kagurabachi / Chapter 0 p94. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: frieren-beyond-journey-s-end / Chapter 1 p20; witch-hat-atelier / Chapter 0 p11; with-you-and-the-rain / Chapter 0 p67. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; only unverified wide source pages.
- CONTINUITY: technical diagram only; petal/sleeve and flower state require special care.
- NOTES: Frieren stands and raises her staff. Needs verified full-body, hand/staff design and restrained flower emergence; a cropped colored strip is not a useful effects lesson.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; ENVIRONMENT_GAP.

### PAGE 13 — NEEDS ATTENTION (integrated p54)

- CAST: Mau; primary Mau; supporting none. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator face/body grounding and V2 stylization available; photo poses and costume do not establish this scene.
- GRAMMAR: the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; am-i-actually-the-strongest / Chapter 0 p6; jujutsu-kaisen / Chapter 0 p94; the-angel-next-door-spoils-me-rotten / Chapter 0 p3; rich-girl-caretaker / Chapter 1 p17; frieren-beyond-journey-s-end / Chapter 1 p20. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; you-and-i-are-polar-opposites / Chapter 1 p24; my-deer-friend-nokotan / Chapter 1 p14. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; no tagged support in the bundle.
- CONTINUITY: technical diagram only; petal/sleeve and flower state require special care.
- NOTES: Mau-only named cast can be intentional visual focus; do not rewrite it. Large flower spread must contrast Scene 1 white-out. Needs flower-field execution, ground plane and true scale.
- BASELINE WARNINGS: ENVIRONMENT_GAP.

### PAGE 14 — NEEDS ATTENTION (integrated p55)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: am-i-actually-the-strongest / Chapter 0 p6; frieren-beyond-journey-s-end / Chapter 1 p20; my-deer-friend-nokotan / Chapter 1 p14; that-time-i-got-reincarnated-as-a-slime / Chapter 0 p21; the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; the-fragant-flower-blooms-with-dignity / Chapter 0 p97. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: jujutsu-kaisen / Chapter 0 p94; witch-hat-atelier / Chapter 0 p11. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; only unverified wide source pages.
- CONTINUITY: technical diagram only; petal/sleeve and flower state require special care.
- NOTES: Mau examines a flower: hand/flower contact and Frieren attentive in the same space. Leafy forest alone does not teach this close interaction.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; ENVIRONMENT_GAP.

### PAGE 15 — NEEDS ATTENTION (integrated p56)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: solo-leveling / Chapter 0 p37; tokyo-ghoul / Chapter 0 p18; jujutsu-kaisen / Chapter 0 p94; am-i-actually-the-strongest / Chapter 0 p6; the-angel-next-door-spoils-me-rotten / Chapter 0 p3; kagurabachi / Chapter 0 p94. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: frieren-beyond-journey-s-end / Chapter 1 p20; witch-hat-atelier / Chapter 0 p11; with-you-and-the-rain / Chapter 0 p67. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; only unverified wide source pages.
- CONTINUITY: technical diagram only; petal/sleeve and flower state require special care.
- NOTES: Overlay says the petal lingers and Frieren brushes it later. Do not move that later gesture into this page automatically. Sleeve continuity cannot be locked while Mau clothing is unapproved.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; ENVIRONMENT_GAP.

### PAGE 16 — NEEDS ATTENTION (integrated p57)

- CAST: Frieren, Mau; primary Frieren; supporting Mau. Matches named script cast; primary is lexical, not a directorial ruling.
- CHARACTER REFS: Mau creator grounding available; Frieren face crop useful, body anchor invalid, wardrobe crop partial; unverified candidates are not identity proof.
- GRAMMAR: the-healer-who-was-banished-from-his-party-is-in-fact-the-strongest / Chapter 1 p17; am-i-actually-the-strongest / Chapter 0 p6; jujutsu-kaisen / Chapter 0 p94; the-angel-next-door-spoils-me-rotten / Chapter 0 p3; rich-girl-caretaker / Chapter 1 p17; the-quintessential-quintuplets / Chapter 0 p22. Layout evidence only; apply the page intent rather than copying source staging.
- TECHNIQUE: kagurabachi / Chapter 0 p94; you-and-i-are-polar-opposites / Chapter 1 p24; frieren-beyond-journey-s-end / Chapter 1 p20. Consult role-mismatch findings above; prefer the small Page 3 selection for restrained acting.
- ENVIRONMENT: Automated gap; only unverified wide source pages.
- CONTINUITY: technical diagram only; petal/sleeve and flower state require special care.
- NOTES: Back shot of both is explicitly required. Existing front photos and false Frieren body reference are inadequate. Need back silhouettes, relative height, flowers and an open horizon; preserve the final line.
- BASELINE WARNINGS: CANDIDATES_IN_BUNDLE; ENVIRONMENT_GAP.

## Frieren review shortlist — visually inspected, not creator-confirmed

| Observation | Source | Useful evidence / limits |
|---|---|---|
| `01a0a2c1-91c6-769e-a10d-745cbed87805` | Ch1 p14 | Side/profile close-up, back hair/robe, conversational confusion. Identify the elf only; other people are not Frieren. |
| `01a0a2c1-91c6-76a0-9c8d-1f828efe6fb2` | Ch2 p13 | Front/slight 3/4 warmth, travel outfit, back/side staff. Strong restrained acting and outdoor staging. The short dark-haired girl is young Fern. |
| `01a0a2c1-91c6-76a3-860a-8e36aa4d466d` | Ch3 p24 | Central frontal face; lower-left actual full body, boots and staff; forest staging. Best replacement for the invalid body anchor. |
| `01a0a2c1-91c6-76a7-a19c-d491c57d50fa` | Ch5 p14 | Profile, robe silhouette and staff context. Combat setting; do not transfer danger/lighting to the quiet scene. |
| `01a0a2c1-91c6-76a8-9fc3-f0e12d0b748d` | Ch6 p7 | Standing full figure and staff in upper-left; lower close-up is Fern, not Frieren. |

Existing verified crop `01a0a2c1-916a-7425-9a40-2037f8a4d714` remains useful for the face. Full manga Ch1 p20 (source unit `77ea902aa2989c594b7e2890f2d0179acfabba88`, offset 19) gives half-lidded/deadpan conversational acting and a restrained slightly annoyed reaction; it is currently craft evidence, not a confirmed corpus anchor.

This set covers front, 3/4, side, body, wardrobe, back and subtle warmth. Annoyance/deadpan can be reviewed on Ch1 p20. Quiet emotional acting is subtle; do not label every neutral panel “sad”. No bulk candidate confirmation or source-series-based identity inference was performed.

## Fern notes

Existing confirmed observation `01a0a2c1-c657-72ed-a04d-accc0a401cd8` genuinely shows Fern in the inn, alongside Frieren. Ch6 p7 (`01a0a2c1-c67b-764e-9113-a4339f6d1e7a`) gives a useful front/upper-body Fern; Ch6 p13 (`01a0a2c1-c67b-764f-abd9-2586388b405a`) gives standing and rear group views with Fern. Ch4 p7/p13 are additional potential front/hair/wardrobe evidence. Do not use the elf's large body panel for Fern. The recurring Frieren Ch123 p13 candidate belongs on a Fern review shortlist. Fern does not block this chapter.

## Environment actions and remaining gaps

Using existing API tagging, added two visually inspected source references:

- `01a0a3ae-0f5a-77c4-a168-ce463743c552`: Ch3 p12, tags forest/trail/vegetation/daylight. Use the forest panels only; this mixed page also includes architecture and a book.
- `01a0a3ae-107f-74f9-867c-438f0aa257aa`: Ch1 p27, tags forest/vegetation/daylight. Useful leafy enclosure and quiet outdoor group spacing; not a flower-field reference.

The seven automated gaps remain on pages 7 and 11–16: missing inherited forest tags and flower-field-specific support are not solved by relabelling forest as flowers. The manual Page 3 pack includes the forest evidence. Existing Spatial Bible v0.2 remains authoritative; no house, lake, sun direction or settlement geography was changed. Its village/inn plan does not authorize moving this scene indoors.

## Page 3 visual pack

Local private deliverable: `m3-review/page3-visual-pack/index.html` beside this task's working files, with `manifest.json` and local image copies. No creator photos or source pixels committed to Git.

- MAU: two creator identity photos + one relaxed standing body/pose photo. Modern clothing excluded.
- STYLE: Mau Anime V2 only as PROJECT_CREATED / SUPPLEMENTAL / STYLIZATION. Clothing rejected.
- FRIEREN: existing face anchor + Ch2 p13 for angle/quiet warmth + Ch3 p24 for real body/wardrobe + Ch1 p14 profile/back. New selections remain review candidates.
- GRAMMAR: Ch1 p20 and Fragrant Flower Ch0 p97, supplemented by the full Ch2 p13 and Ch3 p24 already present. Read RTL, vary scale and retain a pause; never transfer source identity.
- TECHNIQUE: reuse Ch2 p13 for restrained line/expression economy and Ch3 p24 for frontal acting. No duplicate image inflation.
- ENVIRONMENT: Ch3 p12 forest/trail panels, used for visual execution only.
- CONTINUITY: v3 is workflow history. TEST_RENDER pages 1–2 supply no valid prior artwork conditioning.

Each selected image in the manifest has ROLE, WHY SELECTED and WHAT IT TEACHES. This is a review/export pack, not a new production pipeline or injected render attempt.

## Visual experiments

Created one non-canon expression/interaction calibration sheet with Mau front/3/4/profile, Frieren front/3/4/profile and the Page 3 name exchange in RTL close-ups. A second pass removes the initial unintended warm skin tint for a B&W experiment. Both are labelled NON-CANON / EXPLORATORY / SUPPLEMENTAL and not production renders.

The final sheet is `m3-review/non-canon-expression-study-bw.png`; built-in ImageGen prompts are saved locally as `exploration-prompt.txt` and `bw-correction-prompt.txt`. This is not a full Page 3 composition: body staging and wardrobe remain unresolved. A flower-field environment study is deferred at stop condition B. Generated images have not been promoted to identity canon or inserted into the sample.

## GPU status and exact next action

COMFY_LOCAL and COMFY_REMOTE both report not configured. No GPU endpoint was connected, no credentials changed, no alternative pipeline created and no paid render invoked.

Creator: in Frieren's corpus, reject the contents-page body association and the two wrong-character candidates, then confirm Ch3 p24 body/wardrobe and Ch2 p13 face/acting after reviewing the shortlist. Decide Mau's E1 clothing (V2 clothing remains rejected). Then connect the existing ComfyUI backend with checkpoint provenance and supported conditioning. Render ONLY sample Page 3, preserving master/B&W/color lineage, label ARTWORK_CANDIDATE / NON_CANON_SAMPLE / NEEDS HUMAN REVIEW, and stop. Do not mark SAMPLE PASS or begin canonical E1.

## Validation

Specific M3 acceptance suite: passed (19 tests before adding the direct/chapter integration assertions); updated chapter-preview suite: passed (5 tests). Full suite: 569 passed, 1 skipped on Windows (570 collected). The skip is `TestPosixSpecificEscapes::test_absolute_posix_path_rejected`, explicitly POSIX-only filesystem semantics; run `uv run pytest tests/acceptance/test_110_04_traversal.py::TestPosixSpecificEscapes::test_absolute_posix_path_rejected` on Linux to exercise it. Windows-specific tests ran. Existing warnings concern Starlette deprecations and SQLAlchemy's production_page/rough_attempt FK cycle; no failures.

Ruff check/format, strict mypy and import boundaries passed. Web lint and typecheck passed through the existing npm scripts because pnpm was not on this shell's PATH. No web code changed. The first sandboxed test attempt could not access its temporary directory; the authorized rerun completed. No skipped test is counted as passed.
