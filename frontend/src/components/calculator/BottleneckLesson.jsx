import { useEffect, useId, useRef, useState } from 'react'
import { Button } from '../ui/Button'
import { createBottleneckLesson, lessonSummary } from '../../lib/bottleneckLesson'

export function BottleneckLesson({result}) {
 const lesson=createBottleneckLesson(result),id=useId(),heading=useRef(null)
 const [expanded,setExpanded]=useState(false),[phase,setPhase]=useState('learn'),[step,setStep]=useState(0)
 const [answer,setAnswer]=useState(null),[answers,setAnswers]=useState({}),[checked,setChecked]=useState(false)
 function reset(){setPhase('learn');setStep(0);setAnswer(null);setAnswers({});setChecked(false)}
 useEffect(()=>{reset();setExpanded(false)},[lesson?.lessonKey])
 useEffect(()=>{if(expanded)heading.current?.focus()},[phase,step])
 if(!lesson)return null
 const q=lesson.questions[step],summary=lessonSummary(lesson.questions,answers)
 function check(){if(answer===null||checked)return;setAnswers(previous=>({...previous,[q.id]:answer}));setChecked(true)}
 function next(){if(step===lesson.questions.length-1)setPhase('summary');else{setStep(step+1);setAnswer(null);setChecked(false)}}
 return <section className="panel bottleneck-lesson" aria-labelledby={id+'-title'}>
  <div className="lesson-heading"><div><p className="eyebrow">Объяснение и практика · около 3 минут</p><h2 id={id+'-title'}>Почему FPS ограничивает {lesson.kind}?</h2></div><button type="button" className="text-btn" aria-expanded={expanded} aria-controls={id+'-body'} onClick={()=>setExpanded(value=>!value)}>{expanded?'Свернуть':'Разобраться'}</button></div>
  {expanded&&<div id={id+'-body'} className="lesson-body">
   <p className="lesson-context">{lesson.game} · {String(lesson.mode).replaceAll('_',' ')}<br/>{[result.cpuName,result.gpuName].filter(Boolean).join(' + ')}</p>
   {phase==='learn'?<>
    <h3 ref={heading} tabIndex={-1}>Как кадр попадает на экран</h3>
    <div className="lesson-concepts"><article><h4>1. CPU готовит</h4><p>Процессор рассчитывает игровую логику, физику и команды отрисовки. Сложные сцены и высокий целевой FPS могут сильнее нагружать CPU.</p></article><article><h4>2. GPU рисует</h4><p>Видеокарта отрисовывает кадр. Более высокое разрешение, трассировка лучей и тяжёлые эффекты обычно увеличивают её работу.</p></article><article><h4>3. Важен более медленный этап</h4><p>Работа CPU и GPU частично идёт параллельно. В упрощённой модели частоту кадров ограничивает этап, который не успевает за другим. Ускорение второго этапа не гарантирует такой же прирост FPS.</p></article></div>
    <div className="lesson-feedback"><strong>Что это значит для вашего ПК</strong><p>{lesson.diagnosis} Это вывод модели, а не измерение загрузки компонентов.</p>{lesson.currentFrameMs!==null&&<p>Текущий прогноз {result.current_fps} FPS соответствует интервалу между кадрами около {lesson.currentFrameMs.toFixed(2)} мс{lesson.targetFrameMs!==null?`; для цели ${result.target_fps} FPS нужно около ${lesson.targetFrameMs.toFixed(2)} мс`:''}. Это пересчёт 1000 / FPS, а не измеренные CPU/GPU frametime.</p>}</div>
    <p className="field-hint">Ограничение не означает поломку. Перед покупкой проверьте одну и ту же сцену несколько раз: лимит FPS, VSync, температуры и фоновые задачи тоже влияют на результат.</p>
    <div className="lesson-actions"><Button type="button" onClick={()=>setPhase('quiz')}>Проверить понимание — 4 вопроса</Button><button type="button" className="text-btn" onClick={()=>setExpanded(false)}>Закрыть обучение</button></div>
   </>:phase==='quiz'?<>
    <div className="lesson-progress"><span>Вопрос {step+1} из {lesson.questions.length}</span><span>{q.topic}</span></div>
    <h3 className="lesson-question-title" ref={heading} tabIndex={-1}>{q.title}</h3>
    <fieldset className="lesson-question"><legend className="sr-only">Выберите один ответ</legend><div className="lesson-answers">{q.options.map((option,index)=><label key={q.id+'-'+index} className={`${answer===index?'selected':''} ${checked&&index===q.correct?'correct':''} ${checked&&answer===index&&index!==q.correct?'incorrect':''}`}><input type="radio" name={id+'-answer'} checked={answer===index} disabled={checked} onChange={()=>setAnswer(index)}/><span>{option.text}{checked&&index===q.correct&&<strong className="lesson-answer-marker">Правильный ответ</strong>}</span></label>)}</div></fieldset>
    {checked&&<div className="lesson-feedback" role="status"><strong>{answer===q.correct?'Верно':'Разберём, что стоит уточнить'}</strong><p>{q.options[answer].feedback}</p>{answer!==q.correct&&<p>{q.options[q.correct].feedback}</p>}</div>}
    <div className="lesson-actions">{checked?<Button type="button" onClick={next}>{step===lesson.questions.length-1?'Посмотреть результат':'Следующий вопрос'}</Button>:<Button type="button" disabled={answer===null} onClick={check}>Проверить ответ</Button>}<button type="button" className="text-btn" onClick={()=>setExpanded(false)}>Продолжить позже</button></div>
   </>:<>
    <h3 ref={heading} tabIndex={-1}>{summary.correct} из {summary.total} с первой попытки</h3>
    <p>{summary.needsReview.length?'Стоит повторить следующие темы:':'Все ответы в этом мини-тесте верны. Теперь проверьте гипотезу на практике.'}</p>
    {summary.needsReview.length>0&&<ul>{summary.needsReview.map(topic=><li key={topic}>{topic}</li>)}</ul>}
    <details className="lesson-review"><summary>Разбор всех вопросов</summary>{lesson.questions.map(question=><article key={question.id}><h4>{question.title}</h4><p>Ваш ответ: {question.options[answers[question.id]]?.text||'Не дан'}</p><p><strong>Правильный ответ:</strong> {question.options[question.correct].text}</p><p>{question.options[question.correct].feedback}</p></article>)}</details>
    <div className="lesson-feedback"><strong>Что попробовать в игре</strong><p>Запишите FPS и время кадра в одной сцене. Затем снизьте разрешение, сохранив остальное. Заметный рост FPS указывает на возможное ограничение GPU; небольшой рост может указывать на CPU, лимит кадров или другие причины. Проверьте несколько показателей, прежде чем покупать деталь.</p></div>
    <div className="lesson-actions"><Button type="button" variant="secondary" onClick={reset}>Повторить объяснение и тест</Button><button type="button" className="text-btn" onClick={()=>setExpanded(false)}>Вернуться к сборке</button></div>
   </>}
  </div>}
 </section>
}
