import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'

export function BottleneckLesson({ result }) {
  const [step, setStep] = useState(0)
  const [answer, setAnswer] = useState(null)
  const [checked, setChecked] = useState(false)
  const [complete, setComplete] = useState(false)
  const [expanded, setExpanded] = useState(true)
  useEffect(() => { setStep(0); setAnswer(null); setChecked(false); setComplete(false); setExpanded(true) }, [result])
  const cpu = result.bottleneck === 'CPU'
  const component = cpu ? 'процессор (CPU)' : 'видеокарта (GPU)'
  const questions = [
    { title: 'Что сейчас ограничивает FPS в этом расчёте?', options: ['Процессор (CPU)', 'Видеокарта (GPU)', 'Сам по себе объём накопителя'], correct: cpu ? 0 : 1,
      explanation: `По модели для выбранной игры и настроек ограничивает ${component}. Это не означает, что деталь неисправна: она просто медленнее справляется со своей частью работы.` },
    { title: cpu ? 'Почему более мощная видеокарта может почти не повысить FPS?' : 'Почему более мощный процессор может почти не повысить FPS?',
      options: cpu ? ['Процессор не успевает готовить кадры для видеокарты', 'Все видеокарты выдают одинаковый FPS', 'Нужно только увеличить объём SSD'] : ['Видеокарта не успевает отрисовывать кадры', 'Процессор никогда не влияет на игры', 'Нужно только увеличить объём SSD'], correct: 0,
      explanation: cpu ? 'CPU готовит игровую логику и команды, GPU рисует кадр. Если CPU задерживается, более быстрая видеокарта продолжит ждать. Иногда помогают настройки, снижающие нагрузку на CPU.' : 'Когда GPU занят отрисовкой, ускорение CPU не устраняет это ограничение. Снижение разрешения или тяжёлых графических настроек может помочь без покупки новой детали.' },
    { title: 'Будет ли тот же компонент ограничивать ПК во всех играх?', options: ['Да, ограничение всегда одно и то же', 'Нет, оно зависит от игры, разрешения и настроек', 'После апгрейда ограничений больше не бывает'], correct: 1,
      explanation: 'Нагрузка меняется от игры к игре. В высоком разрешении часто сильнее нагружается GPU, а при высоком целевом FPS важен CPU. Проверьте реальные тесты и загрузку компонентов перед покупкой.' },
  ]
  const question = questions[step]
  function next() {
    if (step === questions.length - 1) { setComplete(true); return }
    setStep(step + 1); setAnswer(null); setChecked(false)
  }
  return <section className="panel bottleneck-lesson" aria-label="Разбираемся в ограничении производительности">
    <div className="lesson-heading"><div><p className="eyebrow">Разберёмся за минуту</p><h2>Почему ограничивает {cpu ? 'CPU' : 'GPU'}?</h2></div><button type="button" className="text-btn" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? 'Свернуть' : 'Разобраться'}</button></div>
    {expanded && (complete ? <div className="lesson-complete result-reveal" role="status"><span aria-hidden="true">✓</span><div><h3>Теперь выбор будет осознанным</h3><p>По этому расчёту ограничивает {component}. Сначала сравните настройки и реальные тесты, затем решите, нужен ли апгрейд. Полностью менять ПК для этого необязательно.</p><button type="button" className="text-btn" onClick={() => {setComplete(false);setStep(0);setAnswer(null);setChecked(false)}}>Пройти ещё раз</button></div></div> : <div className="lesson-body">
      <div className="lesson-progress"><span>Вопрос {step + 1} из {questions.length}</span><div aria-hidden="true">{questions.map((_, index) => <i key={index} className={index <= step ? 'active' : ''}/>)}</div><small>Можно пропустить — рекомендации уже доступны ниже</small></div>
      <fieldset className="lesson-question"><legend>{question.title}</legend><div className="lesson-answers">{question.options.map((option, index) => <label key={`${step}-${index}`} className={`${answer === index ? 'selected' : ''} ${checked && index === question.correct ? 'correct' : ''} ${checked && answer === index && index !== question.correct ? 'incorrect' : ''}`}><input type="radio" name="bottleneck-answer" value={index} checked={answer === index} disabled={checked} onChange={() => setAnswer(index)}/><span>{option}</span></label>)}</div></fieldset>
      {checked && <div className="lesson-feedback result-reveal" role="status"><strong>{answer === question.correct ? 'Верно.' : 'Разберём ответ.'}</strong><p>{question.explanation}</p></div>}
      <div className="lesson-actions">{checked ? <Button type="button" onClick={next}>{step === questions.length - 1 ? 'Завершить' : 'Следующий вопрос'}</Button> : <Button type="button" disabled={answer === null} onClick={() => setChecked(true)}>Проверить ответ</Button>}<button type="button" className="text-btn" onClick={() => setExpanded(false)}>Перейти к рекомендации</button></div>
    </div>)}
  </section>
}
