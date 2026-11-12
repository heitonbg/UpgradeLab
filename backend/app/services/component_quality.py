"""Eligibility for critical build parts, separate from price and ad category.

Profiles describe manufacturer specifications, not authenticity of a seller's
item. Unknown models are excluded from automatic builds instead of inventing
certification, internal interfaces, or cooler compatibility.
"""
import json
import re
from app.services.offer_safety import UNSUITABLE


PSUS = [
    (r"\bDEEPCOOL\b.*\bPK550D\b", "DeepCool PK550D", 550, "80 PLUS Bronze",
     "https://www.deepcool.com/products/PowerSupplyUnits/powersupplyunits/PK550D-80-PLUS-Bronze-Power-Supply/2022/15621.shtml/",
     ["SCP", "OPP", "OTP", "OVP", "OCP", "UVP"]),
    (r"\bMSI\b.*\bA650BN\b", "MSI MAG A650BN", 650, "80 PLUS Bronze",
     "https://www.msi.com/Power-Supply/MAG-A650BN/Specification",
     ["OCP", "OVP", "OPP", "OTP", "SCP"]),
    (r"\bDEEPCOOL\b.*\bPK650D\b", "DeepCool PK650D", 650, "80 PLUS Bronze",
     "https://www.deepcool.com/products/PowerSupplyUnits/powersupplyunits/PK650D-80-PLUS-Bronze-Power-Supply/2022/15619.shtml",
     ["SCP", "OPP", "OTP", "OVP", "OCP", "UVP"]),
    (r"\bMSI\b.*\bA750GL\b", "MSI MAG A750GL PCIE5", 750, "80 PLUS Gold",
     "https://www.msi.com/Power-Supply/MAG-A750GL-PCIE5/Specification",
     ["OCP", "OVP", "OPP", "OTP", "SCP", "UVP"]),
]
for watts, sku in [(550, 'cp-9020277-na'), (650, 'cp-9020278-na'), (750, 'cp-9020279-na')]:
    PSUS.append((rf"\bCORSAIR\b.*\bCX{watts}\b", f"Corsair CX{watts}", watts, "80 PLUS Bronze",
                 f"https://www.corsair.com/us/en/p/psu/{sku}/cx-series-cx{watts}-{watts}-watt-80-plus-bronze-atx-power-supply-{sku}", []))
SSDS = [
    (r"\bSAMSUNG\b.*\b870\s*EVO\b", "Samsung 870 EVO",
     "https://semiconductor.samsung.com/consumer-storage/internal-ssd/870evo/"),
    (r"\bKINGSTON\b.*\b(?:S)?KC600\b", "Kingston KC600 2.5″",
     "https://www.kingston.com/en/ssd/kc600-sata-solid-state-drive"),
]
SSDS += [
    (r"\bKINGSTON\b.*\b(?:A400|SA400S37)\b", "Kingston A400",
     "https://www.kingston.com/en/ssd/a400-solid-state-drive"),
    (r"\bCRUCIAL\b.*\b(?:BX500|CT\d+BX500SSD1)\b", "Crucial BX500",
     "https://eu.crucial.com/content/dam/crucial/ssd-products/bx500/flyer/b2c/crucial-bx500-b2c-product-flyer-en.pdf"),
]
SATA_CAPACITIES = {'Samsung 870 EVO': {250, 500, 1000, 2000, 4000},
                   'Kingston KC600 2.5″': {256, 512, 1024, 2048},
                   'Kingston A400': {240, 480, 960}, 'Crucial BX500': {240, 480, 1000, 2000, 4000}}
NVME_SSDS = [
    (r"\bKINGSTON\b.*\b(?:S)?KC3000\b", "Kingston KC3000", {512, 1024, 2048, 4096},
     "https://www.kingston.com/en/ssd/kc3000-nvme-m2-solid-state-drive", "TLC NAND и DRAM-кеш"),
    (r"\b(?:WD|WESTERN DIGITAL)\b.*\bSN580\b", "WD Blue SN580", {500, 1000, 2000},
     "https://documents.westerndigital.com/content/dam/doc-library/en_us/assets/public/western-digital/product/internal-drives/wd-blue-ssd/product-brief-wd-blue-sn580-nvme-ssd.pdf", "nCache 4.0; без выделенного DRAM-кеша"),
]
NVME_SSDS += [
    (r"\bNETAC\b.*\bNV3000[-\s]*Q\b", "Netac NV3000-Q", {512},
     "https://www.netac.com/uploads/20260331/e2b575a1d737b0c4affcac33de563ce9.pdf", "3D NAND; характеристики зависят от ревизии"),
    (r"\bNETAC\b.*\bNV3000\b(?![-\s]*(?:Q|RGB)\b)", "Netac NV3000", {500, 1000, 2000},
     "https://www.netac.com/index.php/index/show?catname=indm2nvme&id=168&lang=en", "3D NAND, HMB и SLC-кеш"),
    (r"\bKINGSPEC\b.*\bNX(?:[-\s]+(?:512(?:GB)?|1TB|2TB|2280))?\b", "KingSpec NX 2280", {512, 1000, 2000},
     "https://kingspecb2b.com/products-catalog/", "3D NAND; тип ячеек и выделенный DRAM не приписываются"),
    (r"\bLEXAR\b.*\bNM620\b", "Lexar NM620", {512, 1000, 2000},
     "https://americas.lexar.com/es/product/lexar-nm620-m-2-2280-nvme-ssd/", "3D TLC NAND"),
    (r"\bCRUCIAL\b.*\bP3\s*PLUS\b", "Crucial P3 Plus", {500, 1000, 2000, 4000},
     "https://www.crucial.com/content/dam/crucial/ssd-products/p3-plus/flyers/b2c/crucial-p3plus-productflyer-consumer.pdf", "Micron 3D NAND; бюджетная серия"),
    (r"\bSAMSUNG\b.*\b980\b(?!\s*PRO)", "Samsung 980", {500, 1000},
     "https://semiconductor.samsung.com/emea/consumer-storage/internal-ssd/980/", "3-битная V-NAND; без выделенного DRAM-кеша"),
]
# Interfaces differ between reviewed series; never claim Gen4 for a Gen3 SSD.
NVME_GENERATIONS = {'Lexar NM620': 3, 'Samsung 980': 3, 'Netac NV3000': 3, 'Netac NV3000-Q': 3, 'KingSpec NX 2280': 3}
SOCKETS = {"AM4", "AM5", "LGA1151", "LGA1200", "LGA1700"}
COOLERS = [
    (r"\bDEEPCOOL\b.*\bAG400\b(?!\s*G2)", "DeepCool AG400",
     "https://www.deepcool.com/products/Cooling/cpuaircoolers/GAMMAXX-AG400-Single-Tower-CPU-Cooler-1851-1700-AM5/2024/15898.shtml"),
    (r"\bDEEPCOOL\b.*\bAG300\b(?!\s*G2)", "DeepCool AG300",
     "https://www.deepcool.com/products/Cooling/cpuaircoolers/AG300-Single-Tower-CPU-Cooler-1700-AM5/2022/16202.shtml"),
]
COOLERS += [
    (r"\bID[\s-]*COOLING\b.*\bSE[\s-]*214[\s-]*XT\b", "ID-COOLING SE-214-XT",
     "https://www.idcooling.com/product/detail?id=482"),
    (r"\bTHERMALRIGHT\b.*\bASSASSIN\s+X\s*120\s+REFINED\s+SE\b", "Thermalright Assassin X 120 Refined SE",
     "https://www.thermalright.com/product/assassin-x-120-refined-se/"),
    (r"\bARCTIC\b.*\bFREEZER\s+36\b(?![\s-]*S\b)", "ARCTIC Freezer 36",
     "https://www.arctic.de/us/Freezer-36"),
]
COOLER_CLASSES = {'DeepCool AG300': 1, 'DeepCool AG400': 2, 'ID-COOLING SE-214-XT': 2,
                  'Thermalright Assassin X 120 Refined SE': 2, 'ARCTIC Freezer 36': 3}
QUALITY_SEARCHES = {
    "psu": ["DeepCool PK550D", "Corsair CX550", "DeepCool PK650D", "Corsair CX650", "MSI MAG A650BN", "Corsair CX750", "MSI MAG A750GL"],
    "storage": ["Netac NV3000 500GB", "Netac NV3000-Q 512GB", "KingSpec NX 512GB 2280", "Lexar NM620 512GB", "Crucial P3 Plus 500GB", "WD Blue SN580 500GB", "Samsung 980 500GB", "Kingston KC3000 512GB", "Crucial BX500 480GB", "Kingston A400 480GB", "Samsung 870 EVO 500GB", "Kingston KC600 512GB"],
    "cooler": ["ID-COOLING SE-214-XT", "Thermalright Assassin X 120 Refined SE", "DeepCool AG400", "DeepCool AG300", "ARCTIC Freezer 36"],
}
ACCESSORIES = re.compile(
    r"креплен|крепёж|крепеж|кронштейн|защ[её]лк|backplate|mounting|bracket|retention|"
    r"переходник|адаптер|adapter|кабел|cable|удлинитель|разветвител|термопаст|термопроклад|"
    r"(?:рамка|винты|болты|стойки|зажимы)\s+(?:для|к)|"
    r"(?:для|for)\s+(?:кулера|блока питания|ssd|samsung|kingston|deepcool)|"
    r"^\s*(?:вентилятор|fan\b|радиатор\b)", re.I)
EXTERNAL = re.compile(r"внешн|external|portable|карман|бокс|enclosure|USB|TYPE[-\s]?C|THUNDERBOLT|m\.?sata|SKC600MS", re.I)
BROKEN = re.compile(r"нерабоч|неисправ|на запчасти|не включается|без вентилятора|без креплен|под ремонт|муляж|коробка без", re.I)


def capacity_gb(title):
    values = []
    for amount, unit in re.findall(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(GB|ГБ|TB|ТБ)\b", title, re.I):
        values.append(round(float(amount.replace(',', '.')) * (1000 if unit.upper() in ('TB', 'ТБ') else 1)))
    sku = re.search(r"S(?:KC600|KC3000[SD]?)/(\d+)G\b", title, re.I)
    if sku:
        values.append(int(sku[1]))
    sata_sku = re.search(r'SA400S37/(\d+)G|CT(\d+)BX500SSD1', title, re.I)
    if sata_sku:
        values.append(int(next(value for value in sata_sku.groups() if value)))
    if len(set(values)) > 1:
        return -1
    return values[0] if values else None


def quality_check(offer, socket=None):
    title = offer.name
    attrs = json.loads(offer.attributes)
    if re.search(r"^\s*(?:игровой\s+)?(?:компьютер|системный блок|ноутбук|моноблок|ПК\b|gaming pc\b)", title, re.I):
        return None, "Это объявление о целом устройстве, а не об отдельной комплектующей."
    if ACCESSORIES.search(title) or BROKEN.search(title) or UNSUITABLE.search(title):
        return None, "Объявление описывает аксессуар, отдельную деталь или неисправный товар."
    used_storage = offer.category == 'storage' and getattr(offer, 'source', None) in ('avito','upgradelab') and offer.condition == 'used'
    if offer.condition != 'new' and not used_storage:
        return None, "Для БП и охлаждения нужны новые детали; б/у SSD допускаются только из выбранного Avito."
    storage_condition = ('Б/у SSD с Avito: запросите SMART, состояние, объём записей и тест полного объёма перед покупкой'
                         if used_storage else 'Новый накопитель')
    if used_storage:
        description = title + ' ' + str(attrs.get('description', ''))
        description = re.sub(r'без ошибок|ошибок нет', '', description, flags=re.I)
        if re.search(r'ошибк[аи].*(?:smart|смарт)|(?:smart|смарт).*(?:ошибк|плох)|bad\s*block|битые сектор|ресурс (?:0|исчерпан)|износ (?:9\d|100)\s*%', description, re.I):
            return None, 'В объявлении указаны ошибки или исчерпанный ресурс SSD.'
    if offer.category == 'psu':
        if re.search(r'\b(?:V[2-9]|REV[. ]*[2-9])\b',title,re.I):
            return None, 'Ревизия БП не подтверждена существующим профилем модели.'
        for pattern, model, watts, rating, url, protections in PSUS:
            if re.search(pattern, title, re.I):
                # A seller's arbitrary '80 Plus' string is not proof of a model.
                if attrs.get('watts') and attrs['watts'] != watts:
                    return None, "Мощность в объявлении расходится с характеристиками модели."
                claimed_watts = [int(value) for value in re.findall(r"\b(\d{3,4})\s*(?:W\b|ВТ\b)", title, re.I)]
                if any(value != watts for value in claimed_watts) or attrs.get('form_factor') not in (None, 'ATX'):
                    return None, "Мощность или форм-фактор объявления не соответствуют модели БП."
                claimed_rating = re.search(r"80\s*(?:PLUS|\+)\s*(BRONZE|GOLD|SILVER|PLATINUM|TITANIUM|WHITE)", title, re.I)
                if claimed_rating and claimed_rating[1].lower() != rating.split()[-1].lower():
                    return None, "В объявлении указан другой класс сертификата, чем в спецификации модели."
                return {"model": model, "label": rating, "watts": watts, "source_url": url,
                        "claims": [f"{watts} Вт · ATX", rating] + (["Защиты: " + ', '.join(protections)] if protections else ["Набор защит проверьте в документации конкретной ревизии"]),
                        "basis": "Характеристики модели по данным производителя; подлинность товара продавца отдельно не проверена."}, None
        return None, "Модель БП не подтверждена: одной надписи «650 Вт» или «80 PLUS» недостаточно."
    if offer.category == 'storage':
        if EXTERNAL.search(title):
            return None, "Нужен внутренний SATA или M.2 NVMe SSD; USB, внешние накопители и mSATA не подходят."
        if str(attrs.get('form_factor', '')).lower() in ('external', 'msata'):
            return None, "Форм-фактор накопителя не подходит для этой сборки."
        capacity = capacity_gb(title)
        stated_capacity = attrs.get('capacity_gb')
        if capacity == -1:
            return None, "В объявлении указано несколько объёмов SSD; цена конкретного варианта не подтверждена."
        if capacity is not None and stated_capacity is not None and capacity != stated_capacity:
            return None, "В объявлении неоднозначно указан объём SSD."
        capacity = capacity or stated_capacity
        if not capacity or capacity < 480:
            return None, "У внутреннего SSD должен быть однозначно указан объём от 480 ГБ."
        for pattern, model, capacities, url, memory in NVME_SSDS:
            if re.search(pattern, title, re.I):
                if capacity not in capacities:
                    return None, "Объём не соответствует вариантам NVMe SSD этой серии."
                interface = str(attrs.get('interface', '')).upper().replace(' ', '')
                form = str(attrs.get('form_factor', '')).lower().replace(' ', '')
                if model == 'KingSpec NX 2280' and not (re.search(r'\b2280\b', title) or form in ('m.22280', '2280')):
                    return None, "Для KingSpec NX нужно подтвердить размер 2280: у семейства есть другие форм-факторы."
                if (interface not in ('', 'NVME', 'PCIE', 'PCIE3.0', 'PCIE3.0X4', 'PCIE4.0', 'PCIE4.0X4', 'PCIENVME') or
                        form not in ('', 'm.2', 'm.22280', '2280') or
                        re.search(r"\bSATA\b|2[.,]5|\b(?:2230|2242|2260|22110)\b", title, re.I)):
                    return None, "Интерфейс или размер объявления не соответствует M.2 2280 NVMe этой модели."
                return {"model": model, "label": "Внутренний M.2 NVMe SSD", "interface": "NVMe", "form_factor": "M.2 2280",
                        "source_url": url, "capacity_gb": capacity,
                        "claims": [f"{capacity} ГБ · M.2 2280 · PCIe {NVME_GENERATIONS.get(model, 4)}.0 x4 NVMe", memory, storage_condition],
                        "condition": offer.condition, "health_verified": False,
                        "basis": "Характеристики модели по данным производителя. Скорость зависит от PCIe платы и CPU; разъём проверяется отдельно."}, None
        for pattern, model, url in SSDS:
            if re.search(pattern, title, re.I):
                if (str(attrs.get('interface', '')).upper() not in ('', 'SATA') or
                        str(attrs.get('form_factor', '')).lower() not in ('', '2.5', '2,5', '2.5″') or
                        re.search(r"NVME|M[.\s]?2", title, re.I)):
                    return None, "Интерфейс или форм-фактор не соответствует SATA 2,5″ этой модели."
                valid_capacities = SATA_CAPACITIES[model]
                if capacity not in valid_capacities:
                    return None, "Указанный объём не соответствует подтверждённым вариантам этой серии SSD."
                return {"model": model, "label": "Внутренний SATA SSD", "interface": "SATA", "source_url": url, "capacity_gb": capacity,
                        "claims": [f"{capacity} ГБ · SATA · 2,5″",
                                   "TLC NAND и DRAM-кеш" if model in ('Samsung 870 EVO', 'Kingston KC600 2.5″') else "Бюджетная серия; тип NAND и DRAM не приписываются без данных ревизии", storage_condition],
                        "condition": offer.condition, "health_verified": False,
                        "basis": "Интерфейс и варианты ёмкости подтверждены для модели по данным производителя."}, None
        return None, "Серия SSD не входит в список моделей с подтверждёнными характеристиками."
    if offer.category == 'cooler':
        for pattern, model, url in COOLERS:
            supported = {'AM4', 'AM5', 'LGA1700'} if model == 'ARCTIC Freezer 36' else SOCKETS
            if re.search(pattern, title, re.I) and socket in supported:
                if attrs.get('sockets') and socket not in attrs['sockets']:
                    return None, "Крепления в этой комплектации не подходят сокету сборки."
                return {"model": model, "label": "Комплектный кулер CPU", "source_url": url, "cooling_class": COOLER_CLASSES[model],
                        "claims": [f"Поддержка {socket} по спецификации", "Радиатор, вентилятор и штатное крепление"],
                        "basis": "Модель кулера и поддержка сокета по данным производителя. Проверьте комплектность при получении."}, None
        return None, "Не подтверждены модель полноценного кулера и поддержка сокета."
    return None, "Категория не проверяется этим правилом."


def invalid_manual_part(name, category):
    if UNSUITABLE.search(name):
        return True
    if category not in QUALITY_SEARCHES:
        return False
    return bool(ACCESSORIES.search(name) or BROKEN.search(name) or (category == 'storage' and EXTERNAL.search(name)))
