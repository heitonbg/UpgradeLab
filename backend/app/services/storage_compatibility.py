"""M.2 alone may mean SATA or Wi-Fi. Never infer NVMe from a chipset/socket."""
import json
import re


def nvme_board_evidence(board):
    if board is None:
        return None
    attrs = json.loads(board.attributes)
    if attrs.get('nvme_2280') is False:
        return None
    if attrs.get('nvme_2280') is True:
        return {'basis': 'В характеристиках предложения платы указан слот M.2 2280 PCIe NVMe.', 'source_url': board.url}
    # Exact reviewed family, not every MSI B550 motherboard.
    if re.search(r'\bMSI\b.*\bB550M[\s-]+PRO[\s-]+VDH\b', board.name, re.I) and not re.search(r'WIFI|MAX|II|V2', board.name, re.I):
        return {'basis': 'MSI B550M PRO-VDH: слоты M.2 Key M, PCIe, формат 2280 по спецификации производителя.',
                'source_url': 'https://www.msi.com/Motherboard/B550M-PRO-VDH/Specification'}
    profiles = [
        (r'\bMSI\b.*\bB550M[\s-]+PRO[\s-]+VDH\s+WIFI\b', 'MSI B550M PRO-VDH WIFI', 'https://www.msi.com/Motherboard/B550M-PRO-VDH-WIFI/Specification'),
        (r'\bMSI\b.*\bB450M[\s-]+A[\s-]+PRO\s+MAX\b', 'MSI B450M-A PRO MAX', 'https://www.msi.com/Motherboard/B450M-A-PRO-MAX/Specification'),
        (r'\bASUS\b.*\bPRIME\s+B550M[\s-]+K\b(?![\s-]*ARGB)', 'ASUS PRIME B550M-K', 'https://www.asus.com/uk/motherboards-components/motherboards/all-series/prime-b550m-k/techspec/'),
        (r'\bGIGABYTE\b.*\bB550M[\s-]+DS3H\b', 'Gigabyte B550M DS3H', 'https://www.gigabyte.com/Motherboard/B550M-DS3H-rev-17'),
        (r'\bASROCK\b.*\bB450M[\s-]+HDV\s+R4[.]0\b', 'ASRock B450M-HDV R4.0', 'https://www.asrock.com/mb/AMD/B450M-HDV%20R4.0/index.asp'),
        (r'\bMSI\b.*\bA520M[\s-]+A[\s-]+PRO\b', 'MSI A520M-A PRO', 'https://www.msi.com/Motherboard/A520M-A-PRO/Specification'),
        (r'\bGIGABYTE\b.*\bH610M[\s-]+K\s+DDR4\b', 'Gigabyte H610M K DDR4', 'https://www.gigabyte.com/Motherboard/H610M-K-DDR4-rev-10/sp'),
        (r'\bMSI\b.*\bPRO[\s-]+B650M[\s-]+B\b', 'MSI PRO B650M-B', 'https://www.msi.com/Motherboard/PRO-B650M-B/Specification'),
        (r'\bMSI\b.*\bPRO[\s-]+H610M[\s-]+E\s+DDR4\b', 'MSI PRO H610M-E DDR4', 'https://www.msi.com/Motherboard/PRO-H610M-E-DDR4/Specification'),
    ]
    for pattern, model, url in profiles:
        variant_mismatch = (bool(re.search(r'WIFI', board.name, re.I)) and 'WIFI' not in model or
                            bool(re.search(r'MAX', board.name, re.I)) and 'MAX' not in model or
                            bool(re.search(r'\bII\b|V2|GEN5', board.name, re.I)))
        if re.search(pattern, board.name, re.I) and not variant_mismatch:
            return {'basis': f'{model}: слот M.2 2280 PCIe по спецификации производителя.', 'source_url': url}
    description = board.name + ' ' + str(attrs.get('description', ''))
    if (re.search(r'M[.\s]?2', description, re.I) and re.search(r'NVME|PCI[- ]?E', description, re.I)
            and re.search(r'\b2280\b', description) and not re.search(r'без\s+(?:слота\s+)?M[.\s]?2|нет\s+M[.\s]?2', description, re.I)):
        return {'basis': 'В характеристиках предложения платы явно указан M.2 2280 PCIe/NVMe; сверьте руководство платы.', 'source_url': board.url}
    return None
