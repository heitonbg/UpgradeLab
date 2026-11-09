import json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import Response,HTTPException
from sqlalchemy import create_engine,inspect,text
from sqlalchemy.orm import Session
from app.db.models import Base,Listing,ListingOwner,User,Hardware
from app.schemas.listing import ListingCreate
from app.api import listings as api

class ListingEditingTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine)
        self.db=Session(self.engine);self.addCleanup(self.engine.dispose);self.addCleanup(self.db.close)
        clock=patch('app.core.price_time.utc_now',return_value=datetime(2026,11,9,12,tzinfo=timezone.utc))
        self.clock=clock.start();self.addCleanup(clock.stop)
        self.user=User(id=1,name='Fixture',email='owner@example.test',password_hash='fixture')
        self.db.add(self.user);self.db.add(Hardware(id=1,type='GPU',name='GeForce RTX 3060 Ti',raw_score=15000,normalized_score=50));self.db.commit()
    def create(self,**extra):
        extra.setdefault('city_id','ru:kemerovo')
        return api.create_listing(ListingCreate(title='GeForce RTX 3060 Ti',condition='Б/У',price='15000',
            contact='iwrawww',**extra),self.db,self.user)
    def test_create_city_model_and_canonical_contact(self):
        row=self.create(city_id='ru:kemerovo',category='GPU',hardware_id=1)
        self.assertEqual(row.city_id,'ru:kemerovo');self.assertEqual(row.contact,'https://t.me/iwrawww')
        self.assertIsNone(row.availability_confirmed_at)
    def test_edit_owner_preserves_publication_and_does_not_confirm(self):
        row=self.create(city_id='ru:kemerovo');created=row.created_at
        self.clock.return_value+=timedelta(hours=1)
        result=api.update_listing(row.id,api.ListingUpdate(description='Новое описание',city_id='ru:kem'),self.db,self.user)
        self.assertEqual(result.created_at,created);self.assertEqual(result.city_id,'ru:kem')
        self.assertIsNone(result.availability_confirmed_at);self.assertIsNotNone(result.updated_at)
    def test_edit_foreign_or_legacy_unowned_listing_is_denied(self):
        row=self.create()
        with self.assertRaises(HTTPException) as error:
            api.update_listing(row.id,api.ListingUpdate(price='1'),self.db,User(id=2))
        self.assertEqual(error.exception.status_code,404);self.assertEqual(row.price,'15000')
    def test_description_and_photo_edit_do_not_refresh_confirmation(self):
        row=self.create(confirm_availability=True)
        confirmed=row.availability_confirmed_at
        self.clock.return_value+=timedelta(hours=1)
        api.update_listing(row.id,api.ListingUpdate(description='Details',photo_url='https://images.example.com/photo.png'),self.db,self.user)
        self.assertEqual(row.availability_confirmed_at,confirmed)
    def test_price_change_invalidates_confirmation(self):
        row=self.create(confirm_availability=True)
        api.update_listing(row.id,api.ListingUpdate(price='16000'),self.db,self.user)
        self.assertIsNone(row.availability_confirmed_at)
    def test_sold_and_withdrawn_are_not_public_results(self):
        for state in ['sold','withdrawn']:
            row=self.create()
            api.update_listing(row.id,api.ListingUpdate(publication_status=state),self.db,self.user)
        self.assertEqual(api.get_listings(self.db),[])
        self.assertEqual(len(api.my_listings(self.db,self.user,Response())),2)
    def test_city_filter_excludes_unknown_and_other_city(self):
        self.create(city_id='ru:kemerovo');self.create(city_id='ru:kem')
        legacy=Listing(title='Legacy',condition='Б/У',price='1000',contact='old',publication_status='active')
        self.db.add(legacy);self.db.commit()
        self.assertEqual(len(api.get_listings(self.db,city_id='ru:kemerovo')),1)
    def test_wrong_catalog_category_rejected_without_mutation(self):
        row=self.create()
        with self.assertRaises(HTTPException):
            api.update_listing(row.id,api.ListingUpdate(category='CPU',hardware_id=1),self.db,self.user)
        self.assertIsNone(row.hardware_id)
    def test_different_model_title_cannot_link_to_selected_gpu(self):
        with self.assertRaises(HTTPException):
            api.create_listing(
                ListingCreate(title='RTX 3060',condition='Б/У',price='15000',contact='@iwrawww',
                              category='GPU',hardware_id=1,city_id='ru:kemerovo'),self.db,self.user)
    def test_remove_photo_and_keep_broken_listing_as_ordinary_ad(self):
        row=self.create(photo_url='https://images.example.com/photo.png')
        result=api.update_listing(row.id,api.ListingUpdate(photo_url=None,condition='Неисправное'),self.db,self.user)
        self.assertIsNone(result.photo_url);self.assertEqual(result.condition,'Неисправное')
    def test_invalid_city_does_not_create_listing(self):
        with self.assertRaises(ValueError):self.create(city_id='unknown-city')

    def test_new_listing_requires_city_but_legacy_edit_keeps_unknown_city(self):
        with self.assertRaises(HTTPException) as error:self.create(city_id=None)
        self.assertEqual(error.exception.status_code,422)
        row=Listing(title='Legacy',condition='Б/У',price='1000',contact='@old',publication_status='active')
        self.db.add(row);self.db.flush();self.db.add(ListingOwner(listing_id=row.id,user_id=self.user.id));self.db.commit()
        result=api.update_listing(row.id,api.ListingUpdate(description='Updated legacy'),self.db,self.user)
        self.assertIsNone(result.city_id)


    def test_ram_model_cannot_be_used_for_another_generation_or_capacity(self):
        self.db.add(Hardware(id=2,type='RAM',name='DDR4 16GB',raw_score=1,normalized_score=1,
                            ram_type='DDR4',ram_capacity_gb=16));self.db.commit()
        payload=ListingCreate(title='DDR5 32GB',condition='Б/У',price='5000',contact='@iwrawww',
                              category='memory',hardware_id=2,city_id='ru:kemerovo')
        with self.assertRaises(HTTPException):api.create_listing(payload,self.db,self.user)

    def test_mobile_gpu_cannot_link_to_desktop_catalogue_model(self):
        payload=ListingCreate(title='GeForce RTX 3060 Ti Laptop',condition='Б/У',price='15000',
            contact='@iwrawww',category='GPU',hardware_id=1,city_id='ru:kemerovo')
        with self.assertRaises(HTTPException):api.create_listing(payload,self.db,self.user)

class ListingMigrationTests(unittest.TestCase):
    def test_additive_migration_is_idempotent_and_preserves_legacy(self):
        from app.db.migrations import migrate_listings
        engine=create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT, condition TEXT, price TEXT, contact TEXT, description TEXT, created_at DATETIME)'))
            conn.execute(text("INSERT INTO listings VALUES (1,'Legacy','Б/У','1000','@old',NULL,'2020-01-01')"))
        migrate_listings(engine);migrate_listings(engine)
        with engine.connect() as conn:
            row=conn.execute(text('SELECT * FROM listings')).mappings().one()
        self.assertEqual(row['title'],'Legacy');self.assertEqual(row['contact'],'@old')
        self.assertEqual(row['publication_status'],'active');self.assertIsNone(row['city_id'])
        self.assertIsNone(row['availability_confirmed_at'])


class SellerAvailabilityTests(unittest.TestCase):
    def test_seller_claim_has_separate_24_hour_policy(self):
        from app.services.listing_validation import seller_availability
        now=datetime(2026,11,9,12,tzinfo=timezone.utc)
        row=Listing(publication_status='active',condition='Б/У',availability_confirmed_at=now)
        with patch('app.core.price_time.utc_now',return_value=now+timedelta(minutes=16)):
            self.assertEqual(seller_availability(row),'seller_declared')
        with patch('app.core.price_time.utc_now',return_value=now+timedelta(hours=24)):
            self.assertEqual(seller_availability(row),'expired')
        row.publication_status='sold'
        self.assertEqual(seller_availability(row),'not_available')
