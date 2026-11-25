type Obj = Record<string, unknown>;
const sceneNames = ["PL Rehearsal – Preshow","PL Rehearsal – Sanctuary","PL Rehearsal – Offering"];
const hash = async (value:string) => btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value)))));
export async function identify(password:string, auth:{salt:string;challenge:string}) {
  return {op:1,d:{rpcVersion:1,eventSubscriptions:4,authentication:await hash(await hash(password+auth.salt)+auth.challenge)}};
}
export const rehearsalScene=(name:string)=>sceneNames.includes(name);
export const confirmedScene=(name:string, observation:Obj)=>observation.currentProgramSceneName===name;
type Pending={resolve:(value:Obj)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>};

/** Rehearsal-only client; no destination, scene collection or output writes. */
export class LocalObs {
  private socket:WebSocket;
  private pending=new Map<string,Pending>();
  private identified=false;

  constructor(password:string, onScene:(name:string)=>void, onStatus:(connected:boolean,message:string)=>void){
    if (!["localhost","127.0.0.1"].includes(window.location.hostname)) throw new Error("Open the dashboard on the OBS computer at localhost to connect.");
    this.socket=new WebSocket("ws://127.0.0.1:4455","obswebsocket.json");
    const handshake=setTimeout(()=>{ onStatus(false,"OBS connection timed out.");this.close(); },5000);
    let oneTimePassword=password;
    this.socket.onmessage=async event=>{
      try {
        const {op,d}=JSON.parse(String(event.data));
        if(op===0){
          if(!d.authentication) throw new Error("Enable password authentication in OBS first.");
          const payload=await identify(oneTimePassword,d.authentication);
          oneTimePassword="";
          if(this.socket.readyState===WebSocket.OPEN) this.socket.send(JSON.stringify(payload));
        }
        if(op===2){
          clearTimeout(handshake);
          this.identified=true;
          await this.assertRehearsal();
          const view=await this.request("GetCurrentProgramScene");
          if(typeof view.currentProgramSceneName === "string") onScene(view.currentProgramSceneName);
          onStatus(true,"OBS connected • local rehearsal");
        }
        if(op===5 && d.eventType==="CurrentProgramSceneChanged" && typeof d.eventData?.sceneName==="string") onScene(d.eventData.sceneName);
        if(op===7){
          const task=this.pending.get(d.requestId);
          if(!task) return;
          clearTimeout(task.timer);this.pending.delete(d.requestId);
          if(d.requestStatus?.result) task.resolve(d.responseData??{});
          else task.reject(new Error(d.requestStatus?.comment??"OBS rejected the request."));
        }
      } catch(error){
        onStatus(false,error instanceof Error?error.message:"OBS connection error.");
        this.close();
      }
    };
    this.socket.onclose=()=>{
      clearTimeout(handshake);oneTimePassword="";this.identified=false;
      for(const task of this.pending.values()){clearTimeout(task.timer);task.reject(new Error("OBS disconnected."));}
      this.pending.clear();
      onStatus(false,"");
    };
    this.socket.onerror=()=>onStatus(false,"Could not reach OBS. Check WebSocket settings.");
  }

  close(){this.socket.close();}

  private request(requestType:string, requestData?:Obj):Promise<Obj>{
    if(!this.identified||this.socket.readyState!==WebSocket.OPEN) return Promise.reject(new Error("OBS is not connected."));
    return new Promise((resolve,reject)=>{
      const requestId=crypto.randomUUID();
      const timer=setTimeout(()=>{this.pending.delete(requestId);reject(new Error("OBS did not confirm the request."));},3500);
      this.pending.set(requestId,{resolve,reject,timer});
      this.socket.send(JSON.stringify({op:6,d:{requestType,requestId,requestData}}));
    });
  }

  private async assertRehearsal(){
    const [collection,output]=await Promise.all([this.request("GetSceneCollectionList"),this.request("GetStreamStatus")]);
    if(collection.currentSceneCollectionName!=="PL Rehearsal") throw new Error("Select the PL Rehearsal scene collection in OBS.");
    if(output.outputActive!==false) throw new Error("Scene controls are blocked while OBS is streaming.");
  }

  async snapshot(name:string){
    const view=await this.request("GetSourceScreenshot",{sourceName:name,imageFormat:"jpg",imageWidth:480});
    const data=view.imageData;
    if(typeof data!=="string"||!/^data:image\/jpe?g;base64,[A-Za-z0-9+/=]+$/i.test(data)||data.length>500000) throw new Error("OBS preview unavailable.");
    return data;
  }

  async take(name:string){
    if(!rehearsalScene(name)) throw new Error("No rehearsal scene mapped for that cue.");
    await this.assertRehearsal();
    await this.request("SetCurrentProgramScene",{sceneName:name});
    if(!confirmedScene(name,await this.request("GetCurrentProgramScene"))) throw new Error("OBS did not confirm the selected scene.");
    return name;
  }
}
