import sys
import unittest
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import Hardware, StoreOffer
from app.services.offers import available_offers
from app.services.prices import price_map


class OfferSafetyTests(unittest.TestCase):
    def test_refurbished_and_repaired_board_are_excluded(self):
        from types import SimpleNamespace as O
        from app.services.offer_safety import safe_offers
        for title in ['Материнская плата MSI PRO H610M-E (Уценка, из ремонта)',
                      'Материнская плата AM4 после ремонта','Материнская плата AM4 восстановленная']:
            row=O(id=1,hardware_id=None,source='oldi',category='motherboard',name=title,
                price_rub=4780,condition='new',attributes='{}')
            self.assertEqual(safe_offers([row],{}),[])

    def test_related_ssd_is_not_stored_as_cpu_and_old_wrong_category_can_be_repaired(self):
        from app.services.offers import upsert
        from app.schemas.offers import OfferInput
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        url='https://www.regard.ru/product/123/ssd'
        with Session(engine) as db:
            row=OfferInput(source='regard',category='CPU',name='Накопитель SSD 500GB Netac NV3000',
                price_rub=10050,url=url,observed_at=datetime.utcnow())
            self.assertEqual(upsert(db,[row],'public_page'),0)
            db.add(StoreOffer(source='regard',category='CPU',name=row.name,price_rub=10050,
                url=url,observed_at=datetime.utcnow(),origin='public_page',attributes='{}',condition='new'))
            db.commit()
            row.category='storage';row.observed_at=datetime.utcnow()
            self.assertEqual(upsert(db,[row],'public_page'),1)
            self.assertEqual(db.query(StoreOffer).one().category,'storage')
        engine.dispose()
    def test_parser_pairs_the_title_with_its_own_link_and_preserves_description(self):
        from app.services.store_providers import parse_html
        html = '''<div data-auto="product-snippet">
          <a href="https://market.yandex.ru/card/gt710/100">Другая ссылка</a>
          <a data-auto="snippet-title" href="https://market.yandex.ru/card/rx6600/200">Radeon RX 6600 8GB</a>
          <span data-auto="snippet-price-current">15000</span>
          <p itemprop="description">Под восстановление, нет изображения</p></div>'''
        row = parse_html('yandex', html, 'GPU')[0]
        self.assertTrue(row.url.endswith('/200'))
        self.assertIn('восстановление', row.attributes['description'])

    def test_mixed_gpu_models_and_restoration_ads_are_rejected_even_from_cache(self):
        from types import SimpleNamespace as O
        from app.services.offer_safety import safe_offers
        from app.services.offers import match_offer
        model = O(id=1, type='GPU', name='Radeon RX 5500', raw_score=12000, vram=8)
        mixed = O(id=1, hardware_id=1, name='Видеокарта Ninja GeForce GT 710 4 ГБ (Radeon RX5500 8GB 128Bit GDDR6), RTL',
                  category='GPU', price_rub=4922, condition='new', source='yandex', attributes='{}', model_name=None)
        self.assertIsNone(match_offer([model], mixed))
        self.assertEqual(safe_offers([mixed], {1: model}), [])
        for title, description in [('B550M PRO-VDH под восстановление', ''),
                                   ('Материнская плата AM4', 'Плата не проверена, на восстановление'),
                                   ('RTX 3060 12GB', 'Нет изображения, донор')]:
            row = O(id=2, hardware_id=None, name=title, category='motherboard', price_rub=10,
                    condition='used', source='avito', attributes=__import__('json').dumps({'description': description}))
            self.assertEqual(safe_offers([row], {}), [])

    def test_existing_cached_ad_is_excluded_from_search_and_build_prices(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Hardware(id=1, type='GPU', name='GeForce RTX 3050 8GB', raw_score=12000, normalized_score=50))
            for index, (name, price, source, condition) in enumerate([
                ('GeForce RTX 3050 8GB', 1111, 'avito', 'used'),
                ('GeForce RTX 3050 8GB обмен', 15000, 'avito', 'used'),
                ('Куплю RTX 3050 8GB', 12000, 'avito', 'used'),
                ('RTX 3050 8GB неисправная', 5000, 'avito', 'used'),
                ('RTX 3050 8GB', 3000, 'avito', 'used'),
                ('RTX 3050 8GB', 20000, 'dns', 'new'),
                ('RTX 3050 8GB', 22000, 'regard', 'new'),
                ('RTX 3050 8GB без обмена', 10000, 'avito', 'used'),
            ], 1):
                db.add(StoreOffer(id=index, hardware_id=1, source=source, category='GPU', name=name,
                                  price_rub=price, condition=condition, url=f'https://example.test/{index}',
                                  attributes='{}', observed_at=datetime.utcnow(), origin='feed'))
            db.commit()
            self.assertEqual([r.id for r in available_offers(db, ['avito'], 'GPU')], [8])
            self.assertEqual(price_map(db, ['avito'])[1].price_rub, 10000)
        engine.dispose()

    def test_old_working_cards_are_not_rejected_only_because_they_are_cheap(self):
        from types import SimpleNamespace as O
        from app.services.offer_safety import safe_offers
        card = O(id=1, hardware_id=2, name='GeForce GTX 750 Ti', category='GPU', price_rub=1800, condition='used', source='avito')
        self.assertEqual(safe_offers([card], {2: O(raw_score=3800)}), [card])


if __name__ == '__main__':
    unittest.main()
