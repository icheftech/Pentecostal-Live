# Sunday Rehearsal Implementation Plan

**Goal:** Rehearse one Sunday from preshow to closing without starting a social broadcast.

**Architecture:** Add a separate /rehearsal route, leaving the regular dashboard and relay untouched. Default to simulation. Opt-in local OBS v5 controls only select verified scenes and observe program state; they never start or stop OBS outputs.

**Tech Stack:** Next.js, React, TypeScript, built-in browser WebSocket and Web Crypto, Node test runner.

**Approved scope:** November 25 operator flow and mockup, with Friday November 27 rehearsal target. Public preshow at 10:15 Central and sanctuary cue at 10:30, with manual Take Live. Offering replaces sanctuary picture and sound. Production keys and deployment are out of scope.

## Review focus

- Zero countdown must not change program; Hold must block any automatic cut while manual Take Live stays usable.
- Selecting a cue must not claim it is on air. In OBS mode, query the actual program scene and observe manual changes.
- OBS disconnect, missing mappings, and command errors must not substitute simulated success.
- Offering privacy is a scene and audio routing requirement, verified against actual output, including at clip end.
- End Rehearsal must be explicit and never end OBS outputs.

## Sequence

- [ ] Test the independent cue state machine with Node, then implement it.
- [ ] Test OBS protocol challenge and status contracts, then implement the localhost-only client.
- [ ] Build the rehearsal route against those interfaces with clear simulation labels and guarded controls.
- [ ] Run tests, lint, and production build; exercise simulated workflow in a browser.
- [ ] Provide booth instructions for an isolated OBS collection and nonpublic recording, including absence of sanctuary audio in Offering.

## Owner-first adjustment

November 25: build the actual authenticated dashboard first, not a separate rehearsal screen. The owner/admin enters the new control room from the existing dashboard. Minimal local OBS session controls work on a separate, named scene collection with active streaming blocked. The booth verification and volunteer rehearsal are later gates. Do not modify the existing production stream controls or main branch.
