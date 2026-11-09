import { useState } from 'react'
import { Modal } from '../ui/Modal'
export function ListingPhoto({ src, alt='Фото объявления', zoom=false }) {
  const [failed,setFailed]=useState(null)
  const [open,setOpen]=useState(false)
  const unavailable=!src || failed===src
  const image=<div className="listing-image-frame">{unavailable
    ? <span className="field-hint" role="img" aria-label="Фото недоступно">Фото недоступно</span>
    : <img src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailed(src)}/>}</div>
  return <>{zoom&&!unavailable?<button type="button" className="listing-image-open" aria-label="Увеличить фото" onClick={()=>setOpen(true)}>{image}</button>:image}
    {open&&<Modal open title="Фото объявления" size="xl" onClose={()=>setOpen(false)}>
      <div className="listing-image-expanded"><img src={src} alt={alt} referrerPolicy="no-referrer" onError={()=>{setFailed(src);setOpen(false)}}/></div>
    </Modal>}
  </>
}
