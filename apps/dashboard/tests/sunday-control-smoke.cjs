const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async()=>{
 const browser=await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE} : {});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  const org={id:"orgtest",name:"PMBC",slug:"pmbc",plan:"pilot"};
  let role="viewer";
  await page.addInitScript(()=>localStorage.setItem("pentecostal_live_token","fixture"));
  await page.route("http://localhost:8000/**",route=>{
   const key=new URL(route.request().url()).pathname;
   const value=({"/v1/auth/me":{user:{id:"u",email:"test@example.test",is_active:true},organization_id:"orgtest",role},"/v1/auth/orgs":[{organization:org,role}],"/v1/organizations/current":org})[key]||[];
   return route.fulfill({json:value,headers:{"access-control-allow-origin":"*"}});
  });
  let scene="PL Rehearsal – Preshow";let streaming=false;let socket;const writes=[];
  await page.routeWebSocket("ws://127.0.0.1:4455/",ws=>{
   socket=ws;
   ws.onMessage(raw=>{
    const {op,d}=JSON.parse(raw);
    if(op===1){assert.ok(d.authentication);ws.send(JSON.stringify({op:2,d:{negotiatedRpcVersion:1}}));}
    if(op!==6)return;
    const {requestType,requestId,requestData}=d;
    if(requestType==="SetCurrentProgramScene"){scene=requestData.sceneName;writes.push(scene);}
    const data=({"GetSceneCollectionList":{currentSceneCollectionName:"PL Rehearsal"},"GetStreamStatus":{outputActive:streaming},"GetCurrentProgramScene":{currentProgramSceneName:scene},"GetSourceScreenshot":{}})[requestType]||{};
    ws.send(JSON.stringify({op:7,d:{requestId,requestType,requestStatus:{result:true,code:100},responseData:data}}));
   });
   ws.send(JSON.stringify({op:0,d:{rpcVersion:1,authentication:{salt:"abc",challenge:"def"}}}));
  });
  await page.goto(process.env.DASHBOARD_TEST_URL ?? "http://127.0.0.1:3000");
  await page.getByText("test@example.test").waitFor();
  assert.equal(await page.getByRole("button",{name:"Open Sunday Control Room"}).count(),0);
  role="owner";await page.reload();
  await page.getByRole("button",{name:"Open Sunday Control Room"}).click();
  await page.getByRole("heading",{name:"Camera Check"}).waitFor();
  await page.getByRole("button",{name:"Add camera"}).click();
  assert.ok(await page.getByText("CAM 4").isVisible());
  await page.getByRole("button",{name:"Broadcast Setup"}).click();
  await page.getByLabel("Local OBS WebSocket password").fill("fixture-password");
  await page.getByRole("button",{name:"Connect local OBS"}).click();
  await page.getByText("OBS connected • local rehearsal").waitFor();
  await page.getByRole("button",{name:"Live Control"}).click();
  await page.getByRole("button",{name:"Hold",exact:true}).click();
  await page.getByRole("button",{name:"Jump near 10:30"}).click();
  await page.clock.install();
  await page.clock.fastForward(11000);
  await page.getByText("00:00 to 10:30 CT").waitFor();
  assert.equal(scene,"PL Rehearsal – Preshow");
  await page.getByRole("button",{name:"Take Live",exact:true}).click();
  await page.getByText("OBS confirmed the program scene.").waitFor();
  assert.equal(scene,"PL Rehearsal – Sanctuary");
  await page.getByRole("button",{name:"Offering Break",exact:true}).click();
  await page.getByRole("region",{name:"Program",exact:true}).getByText("PL Rehearsal – Offering",{exact:false}).waitFor();
  assert.equal(scene,"PL Rehearsal – Offering");
  streaming=true;
  await page.getByRole("button",{name:"Take Live",exact:true}).click();
  await page.getByText("Scene controls are blocked while OBS is streaming.").waitFor();
  assert.equal(writes.length,2);
  streaming=false;
  const offeringButton=page.getByRole("button",{name:"Offering Break",exact:true});
  const program=page.getByRole("region",{name:"Program",exact:true});
  await offeringButton.click();
  await page.getByText("OBS confirmed the program scene.").waitFor();
  assert.equal(writes.length,2,"An already-active Offering scene must not be restarted");
  // Mimic the booth operator taking over directly in OBS, without changing the app's service cue.
  scene="PL Rehearsal – Sanctuary";
  socket.send(JSON.stringify({op:5,d:{eventType:"CurrentProgramSceneChanged",eventIntent:4,eventData:{sceneName:scene}}}));
  await program.getByText("PL Rehearsal – Sanctuary",{exact:false}).waitFor();
  await offeringButton.click();
  await program.getByText("PL Rehearsal – Offering",{exact:false}).waitFor({timeout:2500});
  assert.equal(writes.length,3,"Offering must cut again after a manual return in OBS");
  await page.getByRole("button",{name:"Take Live",exact:true}).click();
  await page.getByRole("region",{name:"Program",exact:true}).getByText("PL Rehearsal – Sanctuary",{exact:false}).waitFor();
  assert.equal(scene,"PL Rehearsal – Sanctuary");
  await page.getByRole("button",{name:"End Rehearsal",exact:true}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Cancel"}).click();
  assert.equal(await page.getByRole("dialog").isVisible(),false);
  socket.close();
  await page.getByText("OBS Offline",{exact:true}).waitFor();
  assert.equal(await page.getByRole("button",{name:"Take Live",exact:true}).isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log("PASS: authenticated dashboard, camera tiles, OBS handshake, Hold past zero, Take Live, Offering with manual OBS recovery, live-output guard, End confirmation, disconnect.");
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
