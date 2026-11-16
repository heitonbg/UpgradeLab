const valid=value=>typeof value==='number'&&Number.isFinite(value)&&value>0
export function createBottleneckLesson(result={}) {
 const kind=['CPU','GPU'].includes(result.bottleneck)?result.bottleneck:null
 if(!kind)return null
 const cpu=kind==='CPU',game=result.config?.game||result.game||'выбранная игра'
 const mode=result.config?.mode||result.calc_mode||'выбранные настройки'
 const component=cpu?'процессор':'видеокарта'
 const diagnosis=`В расчёте для «${game}» ограничивает ${component}. В другой сцене или игре ограничение может измениться.`
 const questions=[
  {id:'diagnosis',topic:'Ограничение в этой конфигурации',title:`Что означает ограничение ${kind} в этом расчёте?`,options:[
   {text:`${component[0].toUpperCase()+component.slice(1)} всегда слабее во всех играх.`,feedback:'Ограничение относится к конкретной игре и настройкам. Универсального процента bottleneck у ПК нет.'},
   {text:cpu?'CPU не успевает готовить кадры так быстро, как GPU мог бы их рисовать.':'GPU не успевает рисовать кадры так быстро, как CPU мог бы их готовить.',feedback:diagnosis},
   {text:`${component[0].toUpperCase()+component.slice(1)} неисправен и требует замены.`,feedback:'Ограничение производительности само по себе не означает поломку.'}],correct:1},
  {id:'upgrade',topic:'Выбор компонента для замены',title:cpu?'Что вероятнее произойдёт при замене только GPU на более мощный?':'Что вероятнее произойдёт при замене только CPU на более мощный?',options:[
   {text:'FPS вырастет пропорционально цене новой детали.',feedback:'Цена детали не задаёт прирост FPS. Важен компонент, который ограничивает выбранный сценарий.'},
   {text:'FPS точно останется тем же в каждой сцене.',feedback:'Это слишком категорично: сцены и характер нагрузки меняются, а наша модель приблизительная.'},
   {text:cpu?'Прирост может быть небольшим: CPU продолжит ограничивать подготовку кадров.':'Прирост может быть небольшим: GPU продолжит ограничивать отрисовку кадров.',feedback:'Замена другого компонента может улучшить отдельные сцены или просадки, но не гарантирует рост среднего FPS. Сравните замеры до покупки.'}],correct:2},
  {id:'settings',topic:'Перенос знания на другие настройки',title:cpu?'Вы снизили разрешение, но FPS почти не вырос. Как это объяснить?':'Вы снизили разрешение, и FPS заметно вырос. Что это подсказывает?',options:[
   {text:cpu?'Снижение нагрузки на GPU могло не помочь, потому что CPU всё ещё ограничивает FPS.':'GPU мог ограничивать FPS: на отрисовку менее подробного кадра требуется меньше работы.',feedback:'Это диагностический признак, а не доказательство. Сравнивайте одну и ту же сцену, проверьте лимит кадров, VSync и другие настройки.'},
   {text:'Разрешение никогда не влияет на производительность.',feedback:'Разрешение меняет объём работы GPU. Эффект зависит от текущего ограничения.'},
   {text:'Это точно доказывает неисправность второго компонента.',feedback:'Один такой эксперимент не диагностирует поломку. Возможны лимит FPS, смена сцены и другие причины.'}],correct:0},
  {id:'verification',topic:'Проверка гипотезы перед покупкой',title:'Как проверить вывод модели перед апгрейдом?',options:[
   {text:'Посмотреть только общий процент загрузки CPU.',feedback:'Общая загрузка CPU может быть низкой при ограничении одного игрового потока. Один показатель не объясняет всю систему.'},
   {text:'Сравнить повторные прогоны одной сцены, frametime и загрузку GPU/потоков CPU, проверить лимиты FPS и тесты нужной конфигурации.',feedback:'Верно: одинаковые условия и несколько показателей помогают проверить гипотезу. Важны также 1% low, температуры, частоты и фоновые задачи.'},
   {text:'Принять расчётные FPS за результат игрового теста.',feedback:'Прогноз модели — гипотеза. Он не заменяет измерение на конкретной системе.'}],correct:1},
 ]
 return {kind,component,game,mode,diagnosis,questions,
  currentFrameMs:valid(result.current_fps)?1000/result.current_fps:null,
  targetFrameMs:valid(result.target_fps)?1000/result.target_fps:null,
  lessonKey:JSON.stringify([kind,game,mode,result.cpuName,result.gpuName,result.current_fps,result.target_fps])}
}
export function lessonSummary(questions,answers) {
 const submitted=questions.filter(q=>Number.isInteger(answers[q.id])&&q.options[answers[q.id]])
 const correct=submitted.filter(q=>answers[q.id]===q.correct).length
 return {correct,answered:submitted.length,total:questions.length,needsReview:submitted.filter(q=>answers[q.id]!==q.correct).map(q=>q.topic)}
}
