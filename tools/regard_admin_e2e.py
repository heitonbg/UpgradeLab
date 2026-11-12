"""Browser acceptance against the isolated local Regard analysis copy only."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / '.artifacts' / 'regard-admin-preview-20261111'
BASE = 'http://127.0.0.1:5174'
TOKEN = (PREVIEW / 'admin-token.txt').read_text(encoding='utf-8').strip()
if not TOKEN:
    raise RuntimeError('Local admin token file is empty')

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        headless=True,
    )
    context = browser.new_context(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce')
    page = context.new_page()
    external_requests = []
    page.route('**/*', lambda route: route.continue_()
               if urlsplit(route.request.url).hostname in ('127.0.0.1', 'localhost', None)
               else (external_requests.append(route.request.url), route.abort()))

    anonymous = context.request.get(BASE + '/api/admin/catalog/regard')
    assert anonymous.status == 403, anonymous.status
    ordinary = context.request.get(BASE + '/api/offers/status')
    assert ordinary.status == 200, ordinary.status
    ordinary_data = ordinary.json()
    public_regard_count = next(item['fresh_offers'] for item in ordinary_data['sources'] if item['source'] == 'regard')
    assert public_regard_count == 0, public_regard_count
    normal_search = context.request.post(BASE + '/api/offers/search', data={
        'query': 'Ryzen 9 9900X', 'category': 'CPU', 'sources': ['regard'], 'method': 'http'})
    assert normal_search.status == 200, normal_search.status
    assert normal_search.json()['offers'] == []

    page.goto(BASE + '/?tab=search', wait_until='networkidle')
    assert page.locator('.regard-admin-panel').count() == 0
    page.goto(BASE + '/?tab=search&regard_admin=1', wait_until='networkidle')
    assert page.locator('.regard-admin-panel').count() == 1
    panel = page.locator('.regard-admin-panel')
    panel.locator('summary').click()
    panel.get_by_label('Ключ владельца', exact=True).fill(TOKEN)
    panel.get_by_label('Поиск товара', exact=True).fill('Ryzen 9 9900X')
    category = panel.get_by_role('combobox', name='Категория', exact=True)
    category.click()
    page.get_by_role('option', name='Процессоры', exact=True).click()
    panel.get_by_role('button', name='Показать товары', exact=True).click()

    cards = panel.locator('.regard-admin-card')
    expect(cards).to_have_count(2)
    expect(panel).to_contain_text('Регард · закрытый локальный каталог')
    expect(cards.first).to_contain_text('Процессор AMD Ryzen 9 9900X OEM')
    expect(cards.first).to_contain_text('35 990')
    expect(cards.first).to_contain_text('Фото в прайсе не указано')
    expect(cards.first).to_contain_text('Ссылка в прайсе отсутствует')
    admin_data = context.request.get(BASE + '/api/admin/catalog/regard?q=Ryzen%209%209900X&category=CPU',
                                     headers={'X-UpgradeLab-Catalog-Admin': TOKEN}).json()
    assert admin_data['total'] == 2
    public_history = context.request.get(BASE + '/api/products/' + admin_data['items'][0]['product_key'] + '/price-history?days=14')
    assert public_history.status == 404, public_history.status
    cards.first.get_by_role('button', name='История цены', exact=True).click()
    expect(cards.first).to_contain_text('2026')
    assert not external_requests, external_requests

    PREVIEW.mkdir(parents=True, exist_ok=True)
    panel.locator('.regard-admin-grid').screenshot(path=str(PREVIEW / 'regard-admin-real-cards.png'))
    print(json.dumps({
        'result': 'ok',
        'cards_in_search': cards.count(),
        'source_date': '2026-11-10',
        'ordinary_public_regard_offers': public_regard_count,
        'ordinary_search_offers': len(normal_search.json()['offers']),
        'history_visible': True,
        'external_requests': len(external_requests),
        'screenshot': str(PREVIEW / 'regard-admin-real-cards.png'),
    }, ensure_ascii=False))
    context.close()
    browser.close()
