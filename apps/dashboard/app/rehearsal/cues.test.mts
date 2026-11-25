import { test } from "node:test";
import assert from "node:assert/strict";
import { cues, countdown, initial, reduce } from "./cues.ts";

test("selecting a cue does not take it live; hold permits an intentional take", () => {
  let state = initial();
  state = reduce(state, { type: "hold" });
  state = reduce(state, { type: "select", index: 3 });
  assert.equal(cues[state.program].id, "preshow");
  assert.equal(state.held, true);
  state = reduce(state, { type: "take" });
  assert.equal(cues[state.program].id, "ministry");
  assert.equal(state.held, false);
});

test("after a break, Take Live restores the staged sanctuary cue", () => {
  let state = reduce(initial(), { type: "take" });
  state = reduce(state, { type: "offer" });
  assert.equal(cues[state.program].id, "offering");
  assert.equal(cues[state.preview].id, "devotion");
  state = reduce(state, { type: "take" });
  assert.equal(cues[state.program].id, "devotion");
});

test("countdown clamps at zero and cannot transition", () => {
  assert.equal(countdown(899), "00:01");
  assert.equal(countdown(900), "00:00");
  assert.equal(countdown(980), "00:00");
  assert.equal(initial().program, 0);
});

test("ending rehearsal locks cue actions until reset", () => {
  const ended = reduce(initial(), { type: "end" });
  assert.deepEqual(reduce(ended, { type: "take" }), ended);
  assert.deepEqual(reduce(ended, { type: "reset" }), initial());
});
