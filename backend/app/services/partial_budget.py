"""Keep an unfinished shopping plan inside a whole-PC budget."""
CATEGORIES = ('CPU', 'GPU', 'motherboard', 'memory', 'storage', 'psu', 'case', 'cooler')


def planning_reserves(pool, budget):
    # Planning reserves are never offered as product prices. Cheaper real
    # observations may lower them; missing products keep an explicit reserve.
    floors = dict(zip(CATEGORIES, (2500, 5000, 2500, 1500, 2000, 3000, 1500, 800)))
    shares = dict(zip(CATEGORIES, (.10, .25, .08, .05, .07, .08, .05, .025)))
    return {cat: min([max(floors[cat], round(budget * shares[cat]))] +
                    [row.price_rub for row in pool[cat]]) for cat in CATEGORIES}


def partial_budget_plan(pool, budget, preferred_source=None, compatible=None):
    reserves = planning_reserves(pool, budget)
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
        states = next_states[:64]
        if not states:
            return [], {'budget': budget, 'known_parts_subtotal': 0,
                        'reserved_for_missing': sum(reserves.values()), 'budget_remaining': budget}
    rows, subtotal, skipped = states[0]
    return rows, {'budget': budget, 'known_parts_subtotal': subtotal,
                  'reserved_for_missing': skipped, 'budget_remaining': budget - subtotal}
