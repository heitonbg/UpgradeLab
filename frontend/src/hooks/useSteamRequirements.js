import {useEffect,useRef} from 'react'
import {request} from '../api/client'
import {enrichSelectedGame,latestRequirementsVersion,REQUIREMENTS_EVENT} from '../lib/steamRequirements'

export function useSteamRequirements(game) {
  useEffect(()=>{
    if (!game) return
    enrichSelectedGame(game,{send:request,notify:detail=>window.dispatchEvent(new CustomEvent(REQUIREMENTS_EVENT,{detail}))}).catch(()=>{})
  },[game])
}

export function useRequirementsRefresh(game,version,busy,refresh) {
  const handler=useRef(refresh),seen=useRef(null)
  handler.current=refresh
  useEffect(()=>{
    let alive=true
    function update() {
      const next=latestRequirementsVersion(game)
      if (!alive || busy || !game || !next || next===version || seen.current===game+':'+next) return
      seen.current=game+':'+next
      Promise.resolve(handler.current()).catch(()=>{})
    }
    update()
    window.addEventListener(REQUIREMENTS_EVENT,update)
    return ()=>{alive=false;window.removeEventListener(REQUIREMENTS_EVENT,update)}
  },[game,version,busy])
}
