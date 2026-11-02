import { useState } from 'react'
import { request } from '../api/client'

export function ForgotPassword({ onBack }) {
  const [email,setEmail] = useState('')
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [error,setError] = useState('')
  async function submit(event){
    event.preventDefault();setBusy(true);setError('');setMessage('')
    try{setMessage((await request('/api/auth/forgot-password',{method:'POST',body:{email}})).message)}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <form className="panel auth-form" onSubmit={submit}><h1>Восстановление пароля</h1><p>Отправим на вашу почту одноразовую ссылку. Она действует 30 минут.</p><label>Email<input required type="email" autoComplete="email" maxLength="254" value={email} onChange={e=>setEmail(e.target.value)}/></label>{message&&<p role="status">{message}</p>}{error&&<p className="error" role="alert">{error}</p>}<button className="primary-btn" disabled={busy}>{busy?'Отправляем…':'Отправить ссылку'}</button><button type="button" className="secondary-btn" onClick={onBack}>Вернуться ко входу</button></form>
}

export function ResetPassword({ token, onDone }) {
  const [password,setPassword] = useState('')
  const [confirmation,setConfirmation] = useState('')
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  async function submit(event){
    event.preventDefault();setError('')
    if(password!==confirmation){setError('Пароли не совпадают.');return}
    setBusy(true)
    try{const data=await request('/api/auth/reset-password',{method:'POST',body:{token,new_password:password}});onDone(data.message)}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <form className="panel auth-form reset-password-form" onSubmit={submit}><h1>Новый пароль</h1><label>Новый пароль<input required type="password" minLength="8" maxLength="128" autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><label>Повторите пароль<input required type="password" minLength="8" maxLength="128" autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label>{error&&<p role="alert" className="error">{error}</p>}<button className="primary-btn" disabled={busy}>{busy?'Сохраняем…':'Задать новый пароль'}</button><button type="button" className="secondary-btn" onClick={()=>onDone('Запросите новое письмо через «Забыли пароль?», если ссылка истекла.')}>Вернуться ко входу</button></form>
}
