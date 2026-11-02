import { useEffect, useRef, useState } from 'react'
import { Button } from './Button'
import { Icon } from './Icon'

export function useStepFlow(count) {
  const [step, setStep] = useState(0)
  const [furthest, setFurthest] = useState(0)
  const formRef = useRef(null)
  const previous = useRef(0)
  useEffect(() => {
    if (previous.current === step) return
    previous.current = step
    const heading = formRef.current?.querySelector('[data-flow-heading]')
    heading?.focus({ preventScroll: true })
    heading?.scrollIntoView({ block: 'nearest' })
  }, [step])
  function invalidAt(index) {
    return [...(formRef.current?.querySelectorAll(`[data-flow-panel="${index}"] input, [data-flow-panel="${index}"] select`) || [])]
      .find(input => !input.disabled && !input.checkValidity())
  }
  function go(index, guard = () => true) {
    if (index < 0 || index >= count || index > furthest + 1) return
    if (index > step) {
      const invalid = invalidAt(step)
      if (invalid) { invalid.reportValidity(); return }
      if (!guard()) return
    }
    setStep(index)
    setFurthest(value => Math.max(value, index))
  }
  function validateAll() {
    for (let index = 0; index < count; index++) {
      const invalid = invalidAt(index)
      if (invalid) {
        setStep(index)
        requestAnimationFrame(() => invalid.reportValidity())
        return false
      }
    }
    return true
  }
  return { step, furthest, formRef, go, validateAll }
}

export function StepNavigation({ steps, flow, onNavigate, disabled }) {
  return <nav className="flow-navigation" aria-label="Шаги настройки">
    <ol>{steps.map((item, index) => <li key={item.title} className={index === flow.step ? 'current' : index < flow.step ? 'complete' : ''}>
      <button type="button" aria-current={index === flow.step ? 'step' : undefined}
        disabled={disabled || index > flow.furthest} onClick={() => onNavigate(index)}>
        <span className="flow-step-number">{index < flow.step ? <span aria-label="Пройден">✓</span> : String(index + 1).padStart(2, '0')}</span>
        <span><strong>{item.title}</strong><small>{item.short}</small></span>
      </button>
    </li>)}</ol>
    <div className="flow-progress" aria-hidden="true"><span style={{ width: `${(flow.step + 1) / steps.length * 100}%` }}/></div>
  </nav>
}

export function StepHeading({ flow, steps }) {
  return <header className="flow-heading" tabIndex={-1} data-flow-heading>
    <p className="eyebrow">Шаг {flow.step + 1} из {steps.length}</p>
    <h3>{steps[flow.step].heading || steps[flow.step].title}</h3>
    <p>{steps[flow.step].description}</p>
  </header>
}

export function StepFooter({ flow, count, onNext, busy, submitLabel }) {
  return <div className="flow-footer">
    <Button type="button" variant="secondary" disabled={flow.step === 0 || busy} onClick={() => flow.go(flow.step - 1)}>Назад</Button>
    <span>{flow.step + 1} / {count}</span>
    {flow.step < count - 1
      ? <Button key="continue" type="button" onClick={onNext} disabled={busy}>Продолжить<Icon name="arrow" size={16}/></Button>
      : <Button key="submit" type="submit" loading={busy}>{busy ? 'Подождите…' : submitLabel}{!busy && <Icon name="arrow" size={16}/>}</Button>}
  </div>
}

export function ReviewSummary({ items, onEdit }) {
  return <div className="flow-review">{items.map(item => <div className="review-row" key={item.label}>
    <span className="review-icon"><Icon name={item.icon} size={19}/></span>
    <div><small>{item.label}</small><strong>{item.value}</strong>{item.note && <p>{item.note}</p>}</div>
    <button type="button" onClick={() => onEdit(item.step)} aria-label={`Изменить: ${item.label}`}>Изменить</button>
  </div>)}</div>
}
