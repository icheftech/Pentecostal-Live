export const cues = [
  { id:"preshow", label:"Preshow", scene:"PL Rehearsal – Preshow", time:"10:15" },
  { id:"devotion", label:"Devotion & Prayer", scene:"PL Rehearsal – Sanctuary", time:"10:30" },
  { id:"praise", label:"Praise Team", scene:"PL Rehearsal – Sanctuary" },
  { id:"ministry", label:"Ministry Emphasis", scene:"PL Rehearsal – Sanctuary" },
  { id:"altar", label:"Altar Call", scene:"PL Rehearsal – Sanctuary" },
  { id:"song", label:"Song", scene:"PL Rehearsal – Sanctuary" },
  { id:"offering", label:"Offering Break", scene:"PL Rehearsal – Offering" },
  { id:"songs", label:"Optional Songs", scene:"PL Rehearsal – Sanctuary" },
  { id:"sermon", label:"Sermon", scene:"PL Rehearsal – Sanctuary" },
  { id:"discipleship", label:"Call to Discipleship", scene:"PL Rehearsal – Sanctuary" },
  { id:"close", label:"Benediction & Closing", scene:"PL Rehearsal – Sanctuary" },
];
export type State = { program:number; preview:number; held:boolean; ended:boolean };
export type Action = {type:"select";index:number} | {type:"hold"|"take"|"offer"|"end"|"reset"};
export function initial(): State { return {program:0,preview:1,held:false,ended:false}; }
export function reduce(state: State, action: Action): State {
  if (action.type === "reset") return initial();
  if (state.ended) return state;
  switch(action.type) {
    case "select": return cues[action.index] ? {...state,preview:action.index} : state;
    case "hold": return {...state,held:!state.held};
    case "take": return {...state,program:state.preview,preview:Math.min(state.preview+1,cues.length-1),held:false};
    case "offer": {
      const offering = cues.findIndex(cue=>cue.id==="offering");
      if (state.program === offering) return state;
      const resume = state.preview === offering ? offering+1 : state.program === 0 ? state.preview : state.program;
      return {...state,program:offering,preview:resume,held:false};
    }
    case "end": return {...state,ended:true,held:false};
  }
}
export function countdown(elapsedSeconds: number): string {
  const s=Math.max(0,900-Math.max(0,Math.floor(elapsedSeconds)));
  return [Math.floor(s/60),s%60].map(v=>String(v).padStart(2,"0")).join(":");
}
