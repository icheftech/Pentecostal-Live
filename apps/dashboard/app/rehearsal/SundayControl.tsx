"use client";

import { useEffect, useRef, useState } from "react";
/* eslint-disable @next/next/no-img-element -- OBS returns local snapshot data URLs. */
import { AudioLines, Camera, Circle, Clock3, Radio, Video } from "lucide-react";
import { countdown, cues, initial, reduce } from "./cues";
import type { Action } from "./cues";
import { LocalObs } from "./obs";
import styles from "./rehearsal.module.css";

const cameraLabels=["Wide","Pulpit","Choir"];

export default function SundayControl({organizationName, serviceTitle, simulation = false}: {organizationName: string; serviceTitle?: string | null; simulation?: boolean}){
  const [state,setState]=useState(initial);
  const [start,setStart]=useState<number|null>(null);
  const [elapsed,setElapsed]=useState(0);
  const [tab,setTab]=useState("Camera Check");
  const mode = simulation ? "sim" : "obs";
  const [connected,setConnected]=useState(false);
  const [actual,setActual]=useState("");
  const [snapshots,setSnapshots]=useState<Record<string,string>>({});
  const [cameraSources,setCameraSources]=useState<string[]>(["","",""]);
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [confirm,setConfirm]=useState(false);
  const [clip,setClip]=useState("");
  const [clipEnded,setClipEnded]=useState(false);
  const [cameras,setCameras]=useState<string[]>([]);
  const [title,setTitle]=useState(serviceTitle ?? "PMBC Sunday Service");
  const [description,setDescription]=useState("");
  const obs=useRef<LocalObs|null>(null);
  const taking=useRef(false);
  const dialog=useRef<HTMLDialogElement|null>(null);
  const clipUrl=useRef("");
  const program=cues[state.program], preview=cues[state.preview];
  const synced=mode==="sim"||connected&&actual===program.scene;

  useEffect(()=>{
    if(start===null||state.ended) return;
    const timer=window.setInterval(()=>setElapsed(Math.min(900,Math.max(0,Math.floor((Date.now()-start)/1000)))),250);
    return ()=>window.clearInterval(timer);
  },[start,state.ended]);
  useEffect(()=>()=>{obs.current?.close();if(clipUrl.current)URL.revokeObjectURL(clipUrl.current);},[]);
  useEffect(()=>{if(confirm&&!dialog.current?.open)dialog.current?.showModal();else if(!confirm&&dialog.current?.open)dialog.current.close();},[confirm]);

  useEffect(()=>{
    const adapter=obs.current;
    if(!connected||!adapter) return;
    let cancelled=false, pending=false;
    async function capture(){
      if(cancelled||pending||!adapter)return;
      pending=true;
      const names=[...new Set([...(tab==="Live Control"?[actual,preview.scene]:[]),...cameraSources].filter(Boolean))];
      const thumbs:Record<string,string>={};
      // Serial polling keeps the OBS renderer from processing many captures at once.
      for(const name of names){
        if(cancelled)break;
        try{thumbs[name]=await adapter.snapshot(name);}catch{/* Missing sources stay unavailable. */}
      }
      if(!cancelled)setSnapshots(thumbs);
      pending=false;
    }
    void capture();
    const timer=window.setInterval(()=>void capture(),1600);
    return ()=>{cancelled=true;window.clearInterval(timer);};
  },[actual,preview.scene,cameraSources,connected,tab]);

  function clockAt(seconds:number){setElapsed(seconds);setStart(Date.now()-seconds*1000);}
  function act(action:Action){setState(current=>reduce(current,action));}
  function connect(event:React.SubmitEvent<HTMLFormElement>){
    event.preventDefault();
    const field=event.currentTarget.elements.namedItem("password") as HTMLInputElement;
    const secret=field.value;field.value="";
    obs.current?.close();setActual("");setConnected(false);setNotice("Connecting to local OBS…");
    try {
      let next:LocalObs;
      next=new LocalObs(secret,name=>{if(obs.current===next)setActual(name);},(good,message)=>{
        if(obs.current!==next)return;
        setConnected(good);
        if(!good)setActual("");
        if(message)setNotice(message);
        else setNotice(current=>current.startsWith("OBS connected")?"OBS disconnected. Use the controls in OBS directly.":current);
      });
      obs.current=next;
    }catch(error){obs.current=null;setNotice(error instanceof Error?error.message:"Can't connect to OBS.");}
  }
  async function take(action:{type:"take"|"offer"}){
    if(taking.current||state.ended||(mode==="obs"&&!connected))return;
    const candidate=reduce(state,action);
    // OBS can change outside the dashboard, even when the local cue has not changed.
    if(candidate===state&&mode==="sim")return;
    taking.current=true;setBusy(true);
    try {
      if(mode==="obs"){
        if(!obs.current)throw new Error("OBS is unavailable.");
        const connection=obs.current;
        const confirmed=await connection.take(cues[candidate.program].scene);
        if(obs.current!==connection)throw new Error("OBS connection changed. Check the program before continuing.");
        setActual(confirmed);
      }
      setClipEnded(false);
      setState(candidate);
      setNotice(mode==="obs"?"OBS confirmed the program scene.":"");
    }catch(error){setNotice(error instanceof Error?error.message:"Scene change failed. Use OBS directly.");}
    finally{taking.current=false;setBusy(false);}
  }
  function chooseClip(file:File|undefined){
    if(clipUrl.current)URL.revokeObjectURL(clipUrl.current);
    clipUrl.current=file?URL.createObjectURL(file):"";
    setClip(clipUrl.current);setClipEnded(false);
  }

  function monitor(kind:"program"|"preview"){
    const isProgram=kind==="program", cue=isProgram?program:preview;
    if(isProgram&&state.ended)return <div className={styles.feed}><Radio size={30}/><strong>Rehearsal ended</strong></div>;
    if(mode==="obs"){
      const name=isProgram?actual:cue.scene;
      return <div className={styles.feed}>{connected&&snapshots[name]?<img className={styles.still} src={snapshots[name]} alt={`OBS snapshot of ${name}`}/>:<Video size={32}/>}<small>{name||"Program not confirmed"} · {connected&&snapshots[name]?"OBS still preview":"No picture"}</small></div>;
    }
    if(cue.id==="preshow")return <div className={`${styles.feed} ${styles.preshow}`}><small>PMBC · SUNDAY SERVICE</small><strong>Welcome to PMBC</strong><span>Service begins at 10:30 AM CT</span><b>{countdown(elapsed)}</b></div>;
    if(cue.id==="offering")return <div className={`${styles.feed} ${styles.preshow}`}>
      {isProgram&&clip&&!clipEnded?<video src={clip} autoPlay playsInline controls onEnded={()=>setClipEnded(true)} onError={()=>setClipEnded(true)}/>:<><small>ONLINE-ONLY BREAK</small><strong>Giving</strong><span>Sample card · stays up until Take Live</span></>}
    </div>;
    return <div className={`${styles.feed} ${styles.sanctuary}`}><Camera size={27}/><strong>{cue.label}</strong><small>Sanctuary · simulated camera feed</small></div>;
  }

  return <section className={styles.room} aria-label="Sunday Control Room">
    <header className={styles.header}>
      <div className={styles.brand}><Radio size={26}/><div><strong>Pentecostal Live</strong><small>{organizationName} · Sunday Service</small></div></div>
      <div className={styles.status}><span>{mode==="sim"?"Simulation":connected?"OBS Connected":"OBS Offline"}</span><b>OWNER TEST · NO PUBLIC OUTPUT</b><span><Clock3 size={15}/> {countdown(elapsed)} to 10:30 CT</span></div>
    </header>
    <nav aria-label="Rehearsal sections" className={styles.tabs}>{["Camera Check","Broadcast Setup","Live Control"].map(item=><button key={item} aria-pressed={tab===item} onClick={()=>setTab(item)}>{item}</button>)}</nav>
    {notice&&<p role="status" className={styles.notice}>{notice}</p>}
    {tab==="Live Control"&&<>
      <div className={styles.workspace}>
        <div className={styles.stage}>
          <div className={styles.monitors}>
            <section className={styles.program} aria-label="Program"><h2><Circle size={10} fill="currentColor"/> PROGRAM · {state.ended?"ENDED":mode==="sim"?"SIMULATED ON AIR":synced?"OBS CONFIRMED":"CHECK OBS"}</h2>{monitor("program")}</section>
            <section className={styles.preview} aria-label="Preview"><h2><Circle size={10} fill="currentColor"/> PREVIEW · NOT ON AIR</h2>{monitor("preview")}</section>
          </div>
          <section className={styles.panel}><h2>Camera Wall <small>{"OBS STILL PREVIEWS"}</small></h2><CameraWall cameras={cameras} sources={cameraSources} snapshots={connected?snapshots:{}}/></section>
          <div className={styles.actions}>
            <button className={styles.hold} aria-pressed={state.held} disabled={busy||state.ended} onClick={()=>act({type:"hold"})}>{state.held?"Release Hold":"Hold"}</button>
            <button className={styles.take} disabled={busy||state.ended||mode==="obs"&&!connected} onClick={()=>void take({type:"take"})}>Take Live</button>
            <button disabled={busy||state.ended||mode==="obs"&&!connected} onClick={()=>void take({type:"offer"})}>Offering Break</button>
            <button className={styles.end} disabled={busy||state.ended} onClick={()=>setConfirm(true)}>End Rehearsal</button>
          </div>
          {state.held&&<p role="status" className={styles.notice}>Hold active. The current cue stays on program until you take another cue.</p>}
        </div>
        <section className={styles.rail}><h2>Sunday Run of Show</h2><p>Select any cue to stage it. Take Live makes the cut.</p>
          <ol>{cues.map((cue,index)=><li key={cue.id}><button aria-disabled={busy||state.ended} disabled={busy||state.ended} data-current={!state.ended&&synced&&state.program===index} data-next={!state.ended&&state.preview===index} onClick={()=>act({type:"select",index})}>
            <span className={styles.time}>{cue.time??String(index+1).padStart(2,"0")}</span><span>{cue.label}</span>
            {synced&&state.program===index&&!state.ended?<small>PROGRAM</small>:state.preview===index&&!state.ended?<small>STAGED</small>:null}
          </button></li>)}</ol>
        </section>
      </div>
      <footer className={styles.footer}><AudioLines size={17}/> Local test mode · no public destinations
        <button disabled={state.ended} onClick={()=>clockAt(0)}>Start 10:15 clock</button><button disabled={state.ended} onClick={()=>clockAt(890)}>Jump near 10:30</button>
        {state.ended&&<button onClick={()=>{setElapsed(0);setStart(null);act({type:"reset"});}}>Reset rehearsal</button>}
      </footer>
    </>}
    {tab==="Camera Check"&&<section className={styles.panel}><h2>Camera Check</h2><p>Connect OBS in Broadcast Setup. Enter the exact OBS source name for each input to see still previews. Check motion and audio in OBS or on the switcher.</p><CameraWall cameras={cameras} sources={cameraSources} snapshots={connected?snapshots:{}}/><div className={styles.setup}>{cameraSources.map((name,index)=><div key={index}><label>{cameraLabels[index]??`Camera ${index+1}`} OBS source<input value={name} onChange={event=>setCameraSources(values=>values.map((value,i)=>i===index?event.target.value:value))}/></label><label><span><input style={{width:"auto"}} type="checkbox" checked={cameras.includes(String(index))} onChange={event=>setCameras(event.target.checked?[...cameras,String(index)]:cameras.filter(item=>item!==String(index)))}/> Framing checked</span></label></div>)}<button onClick={()=>setCameraSources(values=>[...values,""])}>Add camera</button></div></section>}
    {tab==="Broadcast Setup"&&<section className={styles.panel}><h2>Broadcast Setup</h2><div className={styles.setup}>
      <label>Service title<input value={title} onChange={event=>setTitle(event.target.value)}/></label>
      <label>Description<textarea rows={3} value={description} onChange={event=>setDescription(event.target.value)}/></label>
      {simulation&&<label>Sample offering video<input type="file" accept="video/*" onChange={event=>chooseClip(event.target.files?.[0])}/></label>}
      <p>Production platforms and keys are disabled in this workspace.</p>
      <form onSubmit={connect}><label>Local OBS WebSocket password<input name="password" type="password" autoComplete="off" required/></label><button type="submit" disabled={busy||state.ended}>Connect local OBS</button></form>

      <p>OBS mode requires the <strong>PL Rehearsal</strong> scene collection and no active stream. Start and stop any local test recording directly in OBS.</p>
    </div></section>}
    <dialog ref={dialog} className={styles.dialog} onCancel={()=>setConfirm(false)}><h2>End this rehearsal?</h2><p>This ends the practice session in the dashboard. It does not stop any OBS output.</p><div><button autoFocus onClick={()=>setConfirm(false)}>Cancel</button><button className={styles.end} onClick={()=>{act({type:"end"});setConfirm(false);}}>End rehearsal</button></div></dialog>
  </section>;
}

function CameraWall({cameras,sources,snapshots}:{cameras:string[];sources:string[];snapshots:Record<string,string>}){
  return <div className={styles.cameraWall}>{sources.map((source,index)=><div className={styles.cam} key={index}><div>{snapshots[source]?<img className={styles.still} src={snapshots[source]} alt={`Camera ${index+1} OBS snapshot`}/>:<><Camera size={20}/><span>{source?"No preview":"Source not set"}</span></>}</div><strong>CAM {index+1} · {cameraLabels[index]??source}</strong><small>{cameras.includes(String(index))?"Framing checked":"Not checked"}</small></div>)}</div>;
}
