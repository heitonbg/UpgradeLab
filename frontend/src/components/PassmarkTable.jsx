const sources = {
  CPU: {
    title: 'CPU Mark',
    description: 'Синтетическая сводная оценка многопоточной производительности процессора. Она не является FPS в игре и не заменяет отдельные измерения.',
    url: 'https://www.cpubenchmark.net/cpu_list.php',
    label: 'Открыть официальный список PassMark CPU ↗',
  },
  GPU: {
    title: 'G3D Mark',
    description: 'Сводный результат графических тестов PassMark PerformanceTest. Это синтетическая оценка видеокарты, а не измерение FPS в конкретной игре.',
    url: 'https://www.videocardbenchmark.net/high_end_gpus.html',
    label: 'Открыть официальный список PassMark GPU ↗',
  },
}

export function PassmarkTable({ kind }) {
  const source = sources[kind]
  return <section className="passmark-panel benchmark-reference">
    <header><p className="eyebrow">PassMark · {kind === 'CPU' ? 'процессоры' : 'видеокарты'}</p>
      <h2>{source.title}</h2><p>{source.description}</p>
      <p>Рейтинги и количество пользовательских результатов обновляются у источника. Сайт открывает оригинальную страницу, не копируя таблицу.</p>
    </header>
    <a className="secondary-btn" href={source.url} target="_blank" rel="noopener noreferrer">{source.label}</a>
  </section>
}
