"""Keep an unfinished shopping plan inside a whole-PC budget."""
CATEGORIES = ('CPU', 'GPU', 'motherboard', 'memory', 'storage', 'psu', 'case', 'cooler')


def planning_reserves(pool, budget, ram_types=None, ram_capacity_gb=16):
    # These are budget allocations, not product quotes. RAM is the exception
    # to percentage-only estimates: its floor follows current kit pricing.
    floors = dict(zip(CATEGORIES, (2500, 5000, 2500, 13000, 2000, 3000, 1500, 800)))
    shares = dict(zip(CATEGORIES, (.10, .25, .08, .05, .07, .08, .05, .025)))
    types = {value for value in (ram_types or ('DDR4', 'DDR5')) if value in ('DDR4', 'DDR5')}
    if not types:
        types = {'DDR4', 'DDR5'}
    capacity = max(8, int(ram_capacity_gb or 16))
    ram_floor_by_type = {
        'DDR4': (13000 if capacity <= 16 else 29000 * capacity // 32),
        'DDR5': (28000 if capacity <= 16 else 47000 * capacity // 32),
    }
    floors['memory'] = min(ram_floor_by_type[value] for value in types)
    reserves = {}
    for category in CATEGORIES:
        estimate = max(floors[category], round(budget * shares[category]))
        observed = min([estimate] + [row.price_rub for row in pool[category]])
        reserves[category] = max(floors['memory'], observed) if category == 'memory' else observed
    return reserves


def partial_budget_plan(pool, budget, preferred_source=None, compatible=None, ranker=None,
                        ram_types=None, ram_capacity_gb=16):
    reserves = planning_reserves(pool, budget, ram_types, ram_capacity_gb)
    # Beam search considers skipping an unaffordable category, instead of
    # displaying independent quotes whose combined price exceeds the budget.
    states = [([], 0, 0)]  # rows, quoted cost, reserve for skipped categories
    for index, category in enumerate(CATEGORIES):
        remaining = sum(reserves[c] for c in CATEGORIES[index+1:])
        choices = sorted(pool[category], key=lambda row: (row.price_rub, row.id))
        next_states = []
        for rows, subtotal, skipped in states:
            if subtotal + skipped + reserves[category] + remaining <= budget:
                next_states.append((rows, subtotal, skipped + reserves[category]))
            considered = 0
            for row in choices:
                if compatible is not None and not compatible(rows, row):
                    continue
                considered += 1
                if considered > 12:
                    break
                if subtotal + row.price_rub + skipped + remaining <= budget:
                    next_states.append((rows + [row], subtotal + row.price_rub, skipped))
        next_states.sort(key=lambda state: (-len(state[0]),
            -sum(row.source == preferred_source for row in state[0]) if preferred_source else 0,
            state[1], tuple(row.id for row in state[0])))
        if ranker is not None:
            next_states.sort(key=lambda state:(*ranker(state[0]),len(state[0]),-state[1]),reverse=True)
        states = next_states[:64]
        if not states:
            return [], {'budget': budget, 'known_parts_subtotal': 0,
                        'reserved_for_missing': sum(reserves.values()), 'budget_remaining': budget}
    rows, subtotal, skipped = states[0]
    return rows, {'budget': budget, 'known_parts_subtotal': subtotal,
                  'reserved_for_missing': skipped, 'budget_remaining': budget - subtotal}
