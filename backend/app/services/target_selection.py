"""Select feasible complete PCs using explicit, uncalibrated FPS estimates."""
def target_variants(options,target,prefer_cpu_headroom=False):
    if not options:return []
    balance=lambda o:o[9] if len(o)>9 else 1
    reached=[o for o in options if o[3]>=target]
    first=(min(reached,key=lambda o:(o[2],-balance(o),-o[3],o[0].id,o[1].id)) if reached else
           max(options,key=lambda o:(o[3],-o[2],balance(o),-o[0].id,-o[1].id)))
    if prefer_cpu_headroom:
        # Every option is a complete compatible PC already checked against budget.
        # Keep the GPU and never exchange predicted FPS for CPU Mark alone.
        upgrades=[o for o in options if o[1].id==first[1].id and o[3]>=first[3]
                  and o[0].raw_score>=first[0].raw_score]
        first=max(upgrades,key=lambda o:(o[0].raw_score,o[3],-o[2]))
    chosen=[('recommended','Цель по модели' if reached else 'Ближе всего к цели в бюджете',
             'Более сильный CPU с той же видеокартой в пределах бюджета без снижения прогноза FPS.' if prefer_cpu_headroom else 'Минимальная сумма среди рассмотренных полных сборок, достигающих целевого прогноза FPS.' if reached else
             'Лучший найденный прогноз FPS в бюджете; целевой FPS не достигнут.',first)]
    remaining=[o for o in options if (o[0].id,o[1].id)!=(first[0].id,first[1].id)]
    if remaining:
        best=max(remaining,key=lambda o:(o[3],-o[2],balance(o)))
        chosen.append(('performance','Больше FPS в бюджете','Другой вариант с максимальным найденным прогнозом FPS.',best))
        remaining=[o for o in remaining if (o[0].id,o[1].id)!=(best[0].id,best[1].id)]
    if remaining:
        value=max(remaining,key=lambda o:(o[3]/max(1,o[2]),o[3],-o[2],balance(o)))
        chosen.append(('value','FPS на рубль','Альтернатива с высоким расчётным FPS на рубль.',value))
    return chosen

def target_result_rank(result,target):
    fps=result.get('fps') or 0;cost=result['total_price']
    return (fps>=target,-cost if fps>=target else fps,fps if fps>=target else -cost)
