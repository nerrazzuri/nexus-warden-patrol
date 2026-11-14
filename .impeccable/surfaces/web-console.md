---
version: 1
slug: "web-console"
primary_target: "web/console"
related_targets: []
---

# Surface brief: web console (duty + admin)

Scope: the whole Nexus Warden web console (guard pages and admin pages). Mode: Operate. Build path: code-led (no image generation).
Audience/job: night guard watching and acting on alarms; daytime manager/admin configuring the site. Constraints: PRODUCT.md (colour semantics, e-stop always reachable, CSP self, offline). Audit baseline: wt-webux/audit/uiux/CONSOLIDATED_ISSUES.json (27 issues) must be resolved.

## Direction contract

THESIS: State speaks in safety-sign geometry. Every status a guard must read is drawn as an ISO 7010 sign shape (red ring = prohibited/critical P1, amber triangle = warning P2/low battery, green square = safe/normal, blue disc = mandatory action, i.e. the one thing you must do now) plus colour plus text. Refuses the category default of rounded slate cards with coloured dots and pills.
OWN-WORLD: Graphite night ground (#0E1013) for guard pages, signage-white board (#F5F6F4) for admin pages; signal red #D7262D, signal amber #F2A900, safety green #0F7A3C/#2FB45A, mandatory blue #0B5FA5/#3D8FD8 reserved for selection, focus and the primary action. Barlow (DIN-lineage grotesk) for all UI text, tabular numerals; mono only for codes and addresses. Square-cut corners (2px), 1px rules, no shadows except dialogs, no pills.
STORY: The guard sees at once whether anything is prohibited-red; the one mandatory-blue action (我来处理) is where the eye lands next; everything safe is quiet green squares. Admins work on a bright signboard with the same sign vocabulary.
FIRST VIEWPORT: Left rail nav (200px), top bar with arm state, alarm count sign and the 全部叫停 e-stop at the far right. Full-width P1 band framed in a thick red ring-colour rule, red ring sign + text + mandatory-blue 我来处理. Two video tiles and the site map on the left two-thirds; right column: robots (sign + battery tabular) and today's patrols.
FORM: Impeccable's pick, rank 1 of the grounded list (ISO 7010 safety signage); seed: seed:711a14f76d06e080. Signature move: sign-shape state glyphs (ring / triangle / square / disc) used for every status, count and severity across the console.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Unresolved: whether the phone app follows (user decides after comparison).
