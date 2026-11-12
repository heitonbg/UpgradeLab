import sys
import time
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import Hardware, StoreOffer
from app.schemas.offers import OfferInput, SearchOffers
from app.services.offers import batch_search_offers, upsert
from app.services.search_links import web_search_links


class FreeBatchSearchTests(unittest.TestCase):
    def setUp(self):
        from tests.source_grants import grant_network
        grant_network(self)
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            Hardware(id=1,type='CPU',name='AMD Ryzen 5 5500',socket='AM4',raw_score=15000,normalized_score=50),
            Hardware(id=2,type='GPU',name='GeForce RTX 3050 6GB',raw_score=12000,normalized_score=50,vram=6),
        ])
        self.db.commit()
        self.requests = [SearchOffers(query=name, category=category, sources=['regard','kns'])
            for category,name in [('CPU','Ryzen 5 5500'),('GPU','RTX 3050 6GB')]]
        for request in self.requests:
            request._deadline = time.monotonic() + 10

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_categories_are_fetched_concurrently_but_sql_writes_stay_on_request_thread(self):
        owner = threading.get_ident()
        barrier = threading.Barrier(2, timeout=3)
        workers = set()
        def collect(source, request, *args):
            workers.add(threading.get_ident())
            barrier.wait()
            ident = 1 if request.category == 'CPU' else 2
            row = OfferInput(source=source, category=request.category,
                name='AMD Ryzen 5 5500' if ident == 1 else 'GeForce RTX 3050 6GB',
                price_rub=7000 if ident == 1 else 18000, observed_at=datetime.utcnow(),
                url=f'https://www.regard.ru/product/{ident}/part' if source == 'regard' else f'https://www.kns.ru/product/part-{ident}/')
            return source, [row], 'public_page', 'Page received', {}
        def persist(*args, **kwargs):
            self.assertEqual(threading.get_ident(), owner)
            return upsert(*args, **kwargs)
        with patch('app.services.offers.collect_source',side_effect=collect) as network, patch(
                'app.services.offers.upsert',side_effect=persist):
            result = batch_search_offers(self.db, self.requests)
            again = batch_search_offers(self.db, self.requests)
        self.assertGreaterEqual(len(workers),2)
        self.assertNotIn(owner,workers)
        self.assertEqual(network.call_count,4)
        self.assertEqual(len(result),2)
        self.assertEqual(len(again),2)
        self.assertEqual(len(list(self.db.scalars(select(StoreOffer)))),4)

    def test_batch_commits_once_instead_of_once_per_store_and_query(self):
        with patch('app.services.offers.collect_source',side_effect=lambda source,request,*args:
                (source,[],'public_page','OK',{})),patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            batch_search_offers(self.db,self.requests)
        self.assertEqual(commit.call_count,1)

    def test_one_store_failure_does_not_discard_other_store_quotes(self):
        def read(source, query, category, **kwargs):
            if source == 'kns':raise RuntimeError('HTTP 403')
            return [OfferInput(source=source,category=category,name='AMD Ryzen 5 5500',price_rub=7000,
                observed_at=datetime.utcnow(),url='https://www.regard.ru/product/123/cpu')]
        with patch('app.services.offers.search_public',side_effect=read):
            results = batch_search_offers(self.db,self.requests[:1])
        self.assertEqual(len(list(self.db.scalars(select(StoreOffer)))),1)
        statuses={row['source']:row['status'] for row in results[0]['sources']}
        self.assertEqual(statuses,{'regard':'public_page','kns':'unavailable'})

    def test_expired_batch_starts_no_new_network_work(self):
        for request in self.requests:request._deadline=time.monotonic()-1
        with patch('app.services.offers.search_public') as read:
            results=batch_search_offers(self.db,self.requests)
        read.assert_not_called()
        self.assertTrue(all(row['status']=='timeout' for result in results for row in result['sources']))
        self.assertTrue(all(row['attempted'] is False for result in results for row in result['sources']))

    def test_search_links_cover_all_engines_and_target_avito_without_api_keys(self):
        from urllib.parse import urlsplit,parse_qs
        links=web_search_links('avito','RTX 3050 6GB')
        self.assertEqual({link['label'] for link in links},{'Google','Яндекс','Bing','DuckDuckGo'})
        for link in links:
            url=urlsplit(link['url'])
            query=parse_qs(url.query)
            self.assertEqual(url.scheme,'https')
            text=query.get('q',query.get('text'))[0]
            self.assertEqual(text,'RTX 3050 6GB site:avito.ru')


if __name__ == '__main__':
    unittest.main()
