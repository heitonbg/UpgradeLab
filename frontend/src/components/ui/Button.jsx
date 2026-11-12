export function Button({variant='primary',className='',loading=false,iconOnly=false,children,...props}) {
 const variants={primary:'primary-btn',secondary:'secondary-btn',outline:'outline-btn',ghost:'ghost-btn',danger:'destructive-btn',destructive:'destructive-btn'}
 return <button {...props} className={`ui-button ${variants[variant]||variants.secondary} ${iconOnly?'ui-button-icon':''} ${className}`} disabled={loading||props.disabled} aria-busy={loading||undefined}>{loading&&<span className="loading-ring" aria-hidden="true"/>}{children}</button>
}
