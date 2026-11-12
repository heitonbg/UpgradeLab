import { useCallback, useEffect, useRef, useState } from 'react'
import { Modal } from './Modal'
import { Button } from './Button'
export function useConfirm() {
 const [question,setQuestion]=useState(null),resolver=useRef(null)
 useEffect(()=>()=>resolver.current?.(false),[])
 const confirm=useCallback(options=>new Promise(resolve=>{resolver.current?.(false);resolver.current=resolve;setQuestion(options)}),[])
 function finish(answer){const resolve=resolver.current;resolver.current=null;setQuestion(null);resolve?.(answer)}
 const confirmation=<Modal open={Boolean(question)} onClose={()=>finish(false)} title={question?.title||'Подтвердите действие'} size="sm"><p>{question?.description||'Продолжить?'}</p><div className="result-actions"><Button type="button" variant="secondary" onClick={()=>finish(false)}>{question?.cancel||'Отмена'}</Button><Button type="button" variant="danger" onClick={()=>finish(true)}>{question?.action||'Подтвердить'}</Button></div></Modal>
 return {confirm,confirmation}
}
