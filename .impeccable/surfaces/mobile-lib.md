---
version: 1
slug: "mobile-lib"
primary_target: "mobile/lib"
related_targets: []
---

# Surface brief: phone app (Android + iOS, Flutter)

Scope: the whole Nexus Warden phone app (mobile/lib), every role. Mode: Operate. Build path: code-led (no image generation). Platform: adaptive (Android Material 3 + iOS HIG obligations: safe areas, edge-swipe back, system Back).
Audience/job (user 2026-11-15, all four): guard walking a patrol one-handed; guard in the guard room using the phone as a second screen; off-site manager checking tonight, handling alarms, arming; admin/engineer on site adding robots, mapping, routes, remote diagnostics.
Constraints: PRODUCT.md colour semantics; e-stop reachable from every operational screen; no old function lost (app parity list); guard/operational screens dark, setup screens light (user 2026-11-15); default English, professional terms identical to the web (design/console-v2/en/dict.json); say robot never dog; no modals except where data protection needs focus (one-time codes, password re-entry); equal-width buttons per row; missing role features are absent, not greyed. Teleop stays landscape-only.

## Direction contract

THESIS: The phone has two layers and only two: Now (what is happening and what I do about it) and Site (records and setup as a directory). Refuses the five-tab bottom bar that spreads one incident over Duty, Robots, Map and History.
OWN-WORLD: Web V4 Signpost world unchanged: graphite night #0E1013 for Now, signboard white #F5F6F4 for Site setup pages, signal red/amber/green/mandatory blue each with one job, Barlow tabular, 2px corners, 1px rules, flat except floating sheets and the e-stop.
STORY: Open the app and Now answers "is anything wrong, where, what is each robot doing"; a P1 takes the top of Now with the one blue Take ownership; acting (dispatch, warn, notify, close) happens on the incident screen; everything else is one tap into Site.
FIRST VIEWPORT: Top bar: site name + arm state + clock. Below it a two-segment switch Now | Site. Now: incident strip (red frame, ring, title, place, age, blue Take ownership) or an all-clear line; one live video well with Front/Rear/Thermal; small site map with robots and zones; a row of robot tiles (sign + state + battery); tonight's patrol line. Solid red E-STOP ALL square fixed bottom-right in the thumb zone.
FORM: dealt structure B "Now / Site", rank 7 of the grounded list; seed: seed:92eb930a82257495. Signature move: the thumb-zone E-STOP ALL sign, the only solid red field on the phone, present on every Now screen.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Unresolved: Chinese/English board pairs via the web dict; tablet layout (rail) later.
