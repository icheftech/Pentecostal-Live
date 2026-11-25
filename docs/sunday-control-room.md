# Sunday Control Room: owner test

This is an owner/admin screen in the regular Pentecostal Live dashboard. It is not a separate simulator or a production rollout. The existing stream controls, platform keys and relay are unchanged.

## Start a local owner test

1. Run the dashboard and API as described in the project README. On the OBS computer, open the dashboard at `http://localhost:3000` or `http://127.0.0.1:3000` and sign in as the organization owner or admin.
2. In OBS Studio 28+, create a **separate** scene collection named `PL Rehearsal`. Create exactly these scene names (the long dash matters):
   - `PL Rehearsal – Preshow`
   - `PL Rehearsal – Sanctuary`
   - `PL Rehearsal – Offering`
3. Set the preshow as OBS Program. Enable the local, password-protected obs-websocket service on its default port 4455. No firewall changes or internet exposure are needed. Keep public streaming off. In the dashboard, open **Sunday Control Room → Broadcast Setup** and enter the OBS password there only. It is not saved or sent to the app backend.
4. In **Camera Check**, enter the exact names of individual OBS sources. Add or leave blank as needed. The displayed previews are periodic stills, not real-time video. If OBS only sees the switcher's combined output, use the switcher's multiview for individual inputs.
5. In **Live Control**, choose the staged cue and press **Take Live**. The timer does not cut automatically. Try **Hold** and **Jump near 10:30**, let the clock reach zero and verify the preshow stays on Program. **Offering Break** selects the dedicated OBS scene. **End Rehearsal** ends only the dashboard session; start and stop any local test recording in OBS itself.

## Offering: test both picture and sound

- Put a static PMBC giving card under a nonlooping media source in the Offering scene. Enable restart when active and hide the source when playback ends. Use a sample video for the first test. Keep the sanctuary input out of Offering, including any audio embedded in the switcher feed and any global OBS audio devices.
- Make a local OBS recording while someone speaks into the sanctuary mic. Check the encoded recording through the cut into Offering, the clip ending, the missing-clip fallback, and the manual Take Live back to Sanctuary. No sanctuary speech should be heard during Offering. Keep this separate from the in-room sound system.
- While still connected, take Offering in the dashboard, then switch Program back to Sanctuary directly in OBS. Once the dashboard shows Sanctuary, press **Offering Break** again. It should return to Offering. Press it again while Offering is already on Program and verify the clip does not restart.
- Disconnect the dashboard or WebSocket and check that OBS continues to work directly. Confirm the resulting recording plays. Only mark the booth checked after running this with its real inputs.

## Current limits

The dashboard can observe and switch the isolated OBS collection. It refuses scene writes when OBS reports an active stream; the owner decides when to start a local recording. It does not configure OBS inputs, change live destinations, publish titles, create a giving video, or make a public stream. No volunteer walkthrough is needed until the owner has tested this build.

## Checks for this change

- `npm run typecheck`, `npm run lint`, and `npm run build`.
- With Node 24: `node --test apps/dashboard/app/rehearsal/*.test.mts`.
- Optional browser smoke test with Playwright and its Chromium installed: start the local dashboard and run `node apps/dashboard/tests/sunday-control-smoke.cjs`. It intercepts auth API calls and uses an OBS WebSocket fixture; it never contacts social platforms or OBS. Set `DASHBOARD_TEST_URL` for another localhost port. This does not replace the booth audio and recording checks.
