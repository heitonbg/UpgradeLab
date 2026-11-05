"""Budget allocation and conservative selection requirements, not measured TDP."""
import re


def part_limit(category, budget, flexible=False):
    minimum = {'storage': 3000, 'psu': 3000, 'cooler': 1200,
               'motherboard': 3000, 'memory': 2000, 'case': 1500}[category]
    shares = {'storage': .20, 'psu': .13, 'cooler': .06, 'motherboard': .22, 'memory': .16, 'case': .10}
    if flexible:
        shares.update(motherboard=.32, memory=.30, psu=.20, cooler=.08, storage=.22, case=.15)
    return max(minimum, round(budget * shares[category]))


def psu_requirement(cpu, gpu):
    name = gpu.name.upper()
    # Conservative whole-system selection floors; a vendor's board-specific
    # connector/transient requirements still need checking before purchase.
    if re.search(r'RTX\s*(?:3090|4090|5090)|RX\s*(?:7900|9070)\s*(?:XT|XTX)', name):
        watts = 850
    elif re.search(r'VEGA\s*64|RX\s*(?:6800|6900|6950)\s*XT|RTX\s*(?:3080|4080|5080)', name):
        watts = 750
    elif re.search(r'RTX\s*(?:2060|3050|3060|4060|5060)(?!\s*(?:TI|SUPER))\b|RX\s*(?:5500|5600|6500|6600|7600)(?:\s*XT)?\b', name):
        watts = 550
    elif re.search(r'GTX\s*(?:1050|1650)|GT\s*710', name):
        watts = 450
    else:
        watts = 650
    if re.search(r'\bi[79][\s-]|Ryzen\s+9|\d{4,5}K\b', cpu.name, re.I):
        watts = max(watts, 750)
    return watts


def cooling_requirement(cpu):
    if re.search(r'\bi[79][\s-]|Ryzen\s+9|\d{4,5}K\b', cpu.name, re.I) or cpu.raw_score >= 40000:
        return 3
    if re.search(r'\bi5[\s-]*(?:13|14)\d{3}|Ryzen\s+7', cpu.name, re.I) or cpu.raw_score >= 27000:
        return 2
    return 1


def balanced_options(options, mode=None):
    """Remove worse-for-more-money pairs, keep alternatives near the best FPS.

    Cost is the complete PC in automatic mode. Deterministic sorting prevents
    the value card from becoming an arbitrarily weak, cheap third variant.
    """
    if not options:
        return []
    best_gpu = max(option[1].raw_score for option in options)
    high = mode is not None and mode.value != '1080p_low'
    if high:
        options = [option for option in options if option[1].raw_score >= best_gpu * .70]
    frontier, best_fps = [], -1
    for option in sorted(options, key=lambda o: (o[2], -o[3], o[0].id, o[1].id)):
        if option[3] > best_fps:
            frontier.append(option)
            best_fps = option[3]
    # CPU/GPU tradeoffs outside this band belong to a smaller budget search.
    return [option for option in frontier if option[3] >= best_fps * .85]


def search_queries(budget, socket):
    from app.services.gaming_selection import CPU_SEARCHES
    cpus = list(CPU_SEARCHES[socket])
    if budget <= 60000 and socket == 'AM4':
        cpus = ['Ryzen 5 5500', 'Ryzen 5 5600', 'Ryzen 5 5600X']
    cheaper_cpus = {'AM4': ['Ryzen 5 3600', 'Ryzen 5 2600', 'Ryzen 5 4500'],
                    'AM5': ['Ryzen 5 7500F', 'Ryzen 5 7600'],
                    'LGA1700': ['Core i3-12100F', 'Core i5-12400F'],
                    'LGA1200': ['Core i3-10100F', 'Core i5-10400F'],
                    'LGA1151': ['Core i5-8400', 'Core i5-9400F']}
    cpus = list(dict.fromkeys(cpus + cheaper_cpus[socket]))
    if budget <= 35000:
        entry_cpus = {'AM4':['Ryzen 5 3600','Ryzen 5 2600','Ryzen 5 5500'],
                      'LGA1700':['Core i3-12100F','Core i5-12400F'],
                      'LGA1200':['Core i3-10100F','Core i5-10400F'],
                      'LGA1151':['Core i5-8400','Core i5-9400F']}
        cpus=list(dict.fromkeys(entry_cpus.get(socket,[]) + cpus))
    gpu = (['Radeon RX 6600', 'GeForce RTX 3050 6GB', 'GeForce GTX 1660 SUPER', 'GeForce RTX 2060', 'GeForce RTX 3060', 'GeForce RTX 2060 SUPER'] if budget <= 60000
           else ['GeForce RTX 5060', 'GeForce RTX 4060', 'Radeon RX 7600', 'Radeon RX 6700 XT'])
    gpu += ['Radeon RX 6600', 'GeForce RTX 3060', 'GeForce RTX 2060 SUPER', 'GeForce GTX 1660 SUPER', 'GeForce RTX 2060']
    if budget <= 35000:
        gpu=['GeForce GTX 1660 SUPER','GeForce RTX 2060','Radeon RX 580','GeForce GTX 1060']+gpu
    gpu = list(dict.fromkeys(gpu))
    return {
        'CPU': cpus, 'GPU': gpu,
        'storage': ['Netac NV3000', 'Lexar NM620', 'KingSpec NX 512GB 2280', 'Crucial BX500', 'Kingston A400',
                    'Crucial P3 Plus 500GB', 'WD Blue SN580 500GB', 'Samsung 980 500GB'] +
                   (['Lexar NM620 1TB', 'WD Blue SN580 1TB', 'Kingston KC3000 1TB'] if budget >= 80000 else []),
        'psu': ['DeepCool PK550D', 'MSI MAG A650BN', 'Corsair CX550', 'DeepCool PK650D', 'Corsair CX650'] +
               (['Corsair CX750', 'MSI MAG A750GL'] if budget >= 80000 else []),
        'cooler': ['ID-COOLING SE-214-XT', 'Thermalright Assassin X 120 Refined SE', 'DeepCool AG400', 'DeepCool AG300'] +
                  (['ARCTIC Freezer 36'] if budget >= 80000 else []),
    }
