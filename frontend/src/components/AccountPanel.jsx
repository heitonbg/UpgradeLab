import { useState } from 'react'
import { request } from '../api/client'

export function AuthForm({ onAuth }) {
  const [register, setRegister] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', password: '', remember_me: true })
  const [confirmation, setConfirmation] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault();setError('')
    if (register && form.password !== confirmation) { setError('Пароли не совпадают.');return }
    setBusy(true)
    try { await onAuth(await request(`/api/auth/${register ? 'register' : 'login'}`, { method:'POST', body:form })) }
    catch(e) { setError(e.message) }
    finally { setBusy(false) }
  }
  return <div className="auth-layout"><div className="auth-intro"><p className="eyebrow">Личный кабинет</p><h1>Ваши сборки.<br/>Ваши объявления.</h1><p>Один аккаунт для расчётов и биржи комплектующих. Данные хранятся на сервере и доступны после входа.</p></div><form className="panel auth-form" onSubmit={submit}><div className="auth-tabs"><button type="button" className={!register?'selected':''} onClick={()=>{setRegister(false);setError('')}}>Вход</button><button type="button" className={register?'selected':''} onClick={()=>{setRegister(true);setError('')}}>Регистрация</button></div><h2>{register?'Создать аккаунт':'Войти в аккаунт'}</h2>
    {register && <label>Имя<input required minLength="2" maxLength="80" autoComplete="name" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="Ваше имя"/></label>}
    <label>Email<input required type="email" maxLength="254" autoComplete="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} placeholder="mail@example.com"/></label>
    <label>Пароль<div className="password-field"><input required type={showPassword?'text':'password'} minLength={register?8:1} maxLength="128" autoComplete={register?'new-password':'current-password'} value={form.password} onChange={e=>setForm({...form,password:e.target.value})} placeholder={register?'Не менее 8 символов':'Ваш пароль'}/><button type="button" onClick={()=>setShowPassword(!showPassword)} aria-label={showPassword?'Скрыть пароль':'Показать пароль'}>{showPassword?'Скрыть':'Показать'}</button></div></label>
    {register && <label>Повторите пароль<input required type={showPassword?'text':'password'} minLength="8" maxLength="128" autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label>}
    <label className="checkbox-label"><input type="checkbox" checked={form.remember_me} onChange={e=>setForm({...form,remember_me:e.target.checked})}/><span>Запомнить меня на 30 дней</span></label>
    {error && <p className="error" role="alert">{error}</p>}<button className="primary-btn" disabled={busy}>{busy?'Подождите…':register?'Зарегистрироваться':'Войти'}</button></form></div>
}

export function AccountSettings({ user, onUser, onNotice }) {
  const [name, setName] = useState(user.name)
  const [passwords, setPasswords] = useState({ current_password:'', new_password:'' })
  const [busy, setBusy] = useState('')
  async function save(event, kind) {
    event.preventDefault();setBusy(kind)
    try {
      const data = await request(`/api/auth/${kind}`, {method:kind==='profile'?'PATCH':'POST', body:kind==='profile'?{name}:passwords})
      onUser(data)
      if(kind==='password')setPasswords({current_password:'',new_password:''})
      onNotice(kind==='profile'?'Имя обновлено.':'Пароль изменён. Остальные сеансы завершены.')
    } catch(e) { onNotice(e.message) }
    finally { setBusy('') }
  }
  return <details className="panel account-settings"><summary>Настройки аккаунта</summary><div className="account-grid"><form onSubmit={e=>save(e,'profile')}><h3>Профиль</h3><label>Имя<input required minLength="2" maxLength="80" value={name} onChange={e=>setName(e.target.value)}/></label><p className="field-hint">Email: {user.email}</p><button className="secondary-btn" disabled={!!busy}>{busy==='profile'?'Сохраняем…':'Сохранить имя'}</button></form><form onSubmit={e=>save(e,'password')}><h3>Смена пароля</h3><label>Текущий пароль<input required type="password" maxLength="128" autoComplete="current-password" value={passwords.current_password} onChange={e=>setPasswords({...passwords,current_password:e.target.value})}/></label><label>Новый пароль<input required type="password" minLength="8" maxLength="128" autoComplete="new-password" value={passwords.new_password} onChange={e=>setPasswords({...passwords,new_password:e.target.value})}/></label><button className="secondary-btn" disabled={!!busy}>{busy==='password'?'Сохраняем…':'Изменить пароль'}</button></form></div></details>
}
