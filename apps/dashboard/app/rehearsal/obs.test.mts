import { test } from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import { identify, confirmedScene, rehearsalScene } from "./obs.ts";
test("OBS identify proves the password without including the plaintext",async()=>{
 const sha=(s:string)=>createHash("sha256").update(s).digest("base64");
 assert.deepEqual(await identify("secret",{salt:"salt",challenge:"test"}),{op:1,d:{rpcVersion:1,eventSubscriptions:4,authentication:sha(sha("secretsalt")+"test")}});
});
test("only explicit rehearsal scenes are allowed",()=>{
 assert.equal(rehearsalScene("PL Rehearsal – Offering"),true);
 assert.equal(rehearsalScene("Sunday Production"),false);
 assert.equal(rehearsalScene("PL Rehearsal – Other"),false);
});
test("verified program state requires a separate query and a matching scene",()=>{
 assert.equal(confirmedScene("PL Rehearsal – Offering",{currentProgramSceneName:"PL Rehearsal – Offering"}),true);
 assert.equal(confirmedScene("PL Rehearsal – Offering",{}),false);
 assert.equal(confirmedScene("PL Rehearsal – Offering",{currentProgramSceneName:"PL Rehearsal – Sanctuary"}),false);
});
