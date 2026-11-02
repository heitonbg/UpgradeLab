"""Offline integration checks: python tests/test_recovery_offers.py."""
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from unittest import SkipTest

if __name__ != '__main__':
    raise SkipTest('Run test_recovery_offers.py in its own process to isolate the database and settings.')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as directory:
    os.environ.update(DATABASE_URL="sqlite:///" + (Path(directory) / "features.db").as_posix(),
                      OFFERS_LIVE_SEARCH="false", OFFERS_FEED_FILE="", OFFERS_FEED_URLS="{}", SMTP_HOST="")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import settings
    from app.db.base import SessionLocal, engine
    from app.db.models import PasswordReset, StoreOffer, Hardware
    from app.services.offers import upsert, match_offer
    from app.services.prices import price_map
    from app.services.store_providers import parse_html
    from app.schemas.offers import OfferInput
    from app.services.mail import send_reset_email
    from pydantic import ValidationError
    from sqlalchemy import select

    with TestClient(app) as client:
        email, password = "reset@example.com", "before-reset-password"
        assert client.post('/api/auth/register', json={"name":"Reset Test", "email":email, "password":password}).status_code == 201
        assert client.get('/api/auth/discord/status').status_code == 404
        assert client.get('/api/auth/recovery/status').json() == {"enabled": False}
        assert client.post('/api/auth/forgot-password', json={"email":email}).status_code == 503
        assert client.post('/api/auth/forgot-password', json={"email":"not-email"}).status_code == 422
        settings.smtp_host, settings.smtp_from = "smtp.example.test", "no-reply@example.test"
        old_cookie = client.cookies.get('upgrade_session')
        with patch('app.services.mail.send_reset_email') as mail:
            response = client.post('/api/auth/forgot-password', json={"email":email.upper()})
            assert response.status_code == 202, response.text
            token = mail.call_args.args[1]
            assert token not in response.text and email not in response.text
            with SessionLocal() as db:
                assert db.get(PasswordReset, hashlib.sha256(token.encode()).hexdigest())
            unknown = client.post('/api/auth/forgot-password', json={"email":"missing@example.com"})
            assert unknown.json() == response.json() and mail.call_count == 1
            assert client.post('/api/auth/reset-password', json={"token":token,"new_password":"short"}).status_code == 422
            reset = client.post('/api/auth/reset-password', json={"token":token,"new_password":"after-reset-password"})
            assert reset.status_code == 200, reset.text
            assert client.get('/api/auth/me').status_code == 401
            with TestClient(app, cookies={'upgrade_session':old_cookie}) as old_session:
                assert old_session.get('/api/auth/me').status_code == 401
            assert client.post('/api/auth/reset-password', json={"token":token,"new_password":"another-password"}).status_code == 400
            assert client.post('/api/auth/login', json={"email":email,"password":password}).status_code == 401
            assert client.post('/api/auth/login', json={"email":email,"password":"after-reset-password"}).status_code == 200
            client.post('/api/auth/forgot-password', json={"email":email})
            expired_token = mail.call_args.args[1]
            with SessionLocal() as db:
                db.get(PasswordReset, hashlib.sha256(expired_token.encode()).hexdigest()).expires_at = datetime.utcnow()-timedelta(minutes=1)
                db.commit()
            assert client.post('/api/auth/reset-password', json={"token":expired_token,"new_password":"another-password"}).status_code == 400
            client.post('/api/auth/forgot-password', json={"email":email})
            assert client.post('/api/auth/forgot-password', json={"email":email}).status_code == 429
        with patch('app.services.mail.smtplib.SMTP') as smtp:
            send_reset_email(email, 'private-reset-token')
            smtp.return_value.__enter__.return_value.starttls.assert_called_once()
            message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            assert '/#reset_token=private-reset-token' in message.get_content()
        client.post('/api/auth/register', json={"name":"Delivery Test", "email":"delivery@example.com", "password":"delivery-password"})
        with patch('app.services.mail.send_reset_email', side_effect=RuntimeError('smtp failure')) as failed, patch('app.api.recovery.logger.error') as logger:
            assert client.post('/api/auth/forgot-password', json={"email":"delivery@example.com"}).status_code==202
            failed_token=failed.call_args.args[1]
            assert failed_token not in str(logger.call_args)
            with SessionLocal() as db:
                assert db.get(PasswordReset,hashlib.sha256(failed_token.encode()).hexdigest()) is None

        urls={"ozon":"https://www.ozon.ru/product/test-123/", "avito":"https://www.avito.ru/moskva/tovary_dlya_kompyutera/test_123456789",
              "wb":"https://www.wildberries.ru/catalog/123456/detail.aspx", "yandex":"https://market.yandex.ru/product--test/123456", "dns":"https://www.dns-shop.ru/product/123456/test/"}
        now=datetime.utcnow().isoformat()
        with SessionLocal() as db:
            cpu = Hardware(type="CPU", name="AMD Ryzen 5 9991", raw_score=5000, normalized_score=50, socket="AM4")
            gpu = Hardware(type="GPU", name="GeForce RTX 9991", raw_score=5000, normalized_score=50, vram=12)
            db.add_all([cpu,gpu]);db.commit();cpu_id,gpu_id=cpu.id,gpu.id
        rows=[]
        for source,url in urls.items():
            markup=json.dumps({"@type":"Product","name":"AMD Ryzen 5 9991","url":url,"offers":{"@type":"Offer","price":"2500.00","priceCurrency":"RUB","availability":"https://schema.org/InStock"}})
            parsed=parse_html(source,f'<script type="application/ld+json">{markup}</script>',"CPU")
            assert len(parsed)==1 and parsed[0].price_rub==2500
            rows += parsed
            with SessionLocal() as db:
                upsert(db, parsed, "public_page")
                selected=price_map(db,[source])
                assert selected[cpu_id].source==source and selected[cpu_id].price_rub==2500
            try:
                parse_html(source,'<html>SmartCaptcha</html>',"CPU")
                raise AssertionError('CAPTCHA must not be a successful empty result')
            except RuntimeError:
                pass
        try:
            OfferInput.model_validate({**rows[0].model_dump(),"url":"https://evil.example/product/test"})
            raise AssertionError('Foreign URL accepted')
        except ValidationError:
            pass
        with SessionLocal() as db:
            hardware=list(db.scalars(select(Hardware)))
            wrong=OfferInput(source="ozon",name="AMD Ryzen 5 9991X",model_name="AMD Ryzen 5 9991",category="CPU",url=urls['ozon'],price_rub=100,observed_at=now)
            assert match_offer(hardware,wrong) is None
            mobile=OfferInput(source="ozon",name="GeForce RTX 9991 Laptop",category="GPU",url=urls['ozon'],price_rub=100,observed_at=now)
            assert match_offer(hardware,mobile) is None
            gpu_offer=OfferInput(source="ozon",name="GeForce RTX 9991 12GB",category="GPU",url="https://www.ozon.ru/product/gpu-987/",price_rub=3000,observed_at=now)
            upsert(db,[gpu_offer],"feed")
        search={"query":"Ryzen 5 9991","category":"CPU","sources":["ozon"],"hardware_id":cpu_id}
        with patch('app.services.offers.search_public', return_value=[rows[0]]) as provider:
            settings.offers_live_search=True
            found=client.post('/api/offers/search',json=search)
            assert found.status_code==200 and found.json()['offers'][0]['source']=='ozon',found.text
            assert client.post('/api/offers/search',json=search).status_code==200
            assert provider.call_count==1
        with SessionLocal() as db:
            discounted=rows[1].model_copy(update={"price_rub":2300,"observed_at":datetime.utcnow()})
            upsert(db,[discounted],"feed")
            assert price_map(db,['avito','ozon'])[cpu_id].price_rub==2300
            assert price_map(db,['ozon'])[cpu_id].price_rub==2500
            removed=discounted.model_copy(update={"available":False,"observed_at":datetime.utcnow()})
            upsert(db,[removed],"feed")
            assert cpu_id not in price_map(db,['avito'])
        with patch('app.services.offers.search_public',side_effect=RuntimeError('blocked')):
            blocked=client.post('/api/offers/search',json={**search,"query":"unknown9999","sources":["dns"],"hardware_id":None})
            assert blocked.json()['sources'][0]['status']=='unavailable' and blocked.json()['offers']==[]
        with patch('app.services.browser_offers.search_browser',return_value=([],{"discovered":1,"verified":0,"links":[urls['dns']],"error":"Цена пока не подтверждена"})) as browser:
            discovered=client.post('/api/offers/search',json={**search,"query":"browser unknown","hardware_id":None,"sources":["dns"],"method":"discovery"})
            assert discovered.status_code==200,discovered.text
            assert discovered.json()['offers']==[]
            assert discovered.json()['candidates'][0]['url']==urls['dns']
            assert browser.call_count==1
        settings.offers_feed_urls=json.dumps({"wb":"https://feed.example/wb"})
        settings.offers_feed_tokens=json.dumps({"wb":"private-feed-token"})
        with patch('app.services.offers.fetch',return_value=json.dumps({"offers":[rows[2].model_dump(mode='json')]})) as remote:
            supplied=client.post('/api/offers/search',json={**search,"query":"feed-9991","sources":["wb"]})
            assert supplied.json()['sources'][0]['status']=='feed',supplied.text
            assert remote.call_args.args[2]=='private-feed-token'
            assert 'private-feed-token' not in supplied.text
        settings.offers_feed_urls=settings.offers_feed_tokens='{}'
        markup=json.dumps({"@type":"Product","name":"AMD Ryzen 5 9991","url":urls['ozon'],"offers":{"price":2500,"priceCurrency":"RUB"}})
        with patch('app.api.offers.fetch',return_value=f'<script type="application/ld+json">{markup}</script>'):
            by_link=client.post('/api/offers/from-url',json={"source":"ozon","category":"CPU","url":urls['ozon']+'?utm_source=test'})
            assert by_link.status_code==200 and by_link.json()['price_rub']==2500,by_link.text

        attrs={"motherboard":{"socket":"AM4","ram_type":"DDR4","form_factor":"mATX"},
               "memory":{"ram_type":"DDR4","capacity_gb":16,"modules":2}, "storage":{"interface":"SATA","capacity_gb":500},
               "psu":{"watts":650,"form_factor":"ATX"}, "case":{"board_formats":["mATX"],"psu_formats":["ATX"]},"cooler":{"sockets":["AM4"]}}
        with SessionLocal() as db:
            quality_names={'psu':'MSI MAG A650BN 650W','storage':'Samsung 870 EVO 500GB','cooler':'Кулер DeepCool AG400'}
            supporting=[OfferInput(source="ozon",name=quality_names.get(category,f"Test {category}"),category=category,price_rub=1000,url=f"https://www.ozon.ru/product/test-{category}-123/",observed_at=now,attributes=value) for category,value in attrs.items()]
            upsert(db,supporting,"feed")
        assembly={"scenario":"build","game":"CS2","mode":"1080p_low","budget":15000,"target_fps":60,"socket":"AM4","ram_type":"DDR4","ram_capacity_gb":16,"auto_parts":True,"case_style":"budget","price_sources":["ozon"]}
        result=client.post('/api/assemble',json=assembly)
        assert result.status_code==200,result.text
        assert len(result.json()['parts'])==8 and result.json()['total_price']==11500
        assert all(part['price_url'].startswith('https://www.ozon.ru/') for part in result.json()['parts'])
        assert client.post('/api/builds',json=assembly).status_code==201
        expanded=client.post('/api/assemble',json={**assembly,"price_sources":["dns"]})
        assert expanded.status_code==200 and expanded.json()['status']=='complete',expanded.text
        assert 'ozon' in expanded.json()['search_report']['additional_sources']
        with patch.object(settings,'offers_browser_enabled',False):
            restricted=client.post('/api/assemble',json={**assembly,"price_sources":["dns"],"allow_store_fallback":False})
        assert restricted.status_code==200 and restricted.json()['status']=='partial',restricted.text
        assert restricted.json()['search_report']['additional_sources']==[]
        by_category={part['type']:part for part in result.json()['parts']}
        manual={**assembly,"auto_parts":False,**{key:{"name":"tampered","price":1,"offer_id":by_category[key]['offer_id']} for key in attrs}}
        checked=client.post('/api/assemble',json=manual)
        assert checked.status_code==200 and checked.json()['total_price']==11500,checked.text
        with SessionLocal() as db:
            for offer in db.scalars(select(StoreOffer)):
                offer.observed_at=datetime.utcnow()-timedelta(days=2)
            db.commit()
            assert price_map(db,['ozon'])=={}
        assert client.post('/api/assemble',json=manual).status_code==400
    engine.dispose()
print('Recovery and stores passed: SMTP, one-use/expired tokens, session revocation, throttling, five parsers, exact matching, source filters, automatic parts, server price validation and quote expiry')
