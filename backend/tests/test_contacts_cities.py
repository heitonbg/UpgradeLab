import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.contacts import normalize_contact
from app.services.cities import search_cities, CITIES
class ContactsCitiesTests(unittest.TestCase):
    def test_telegram_variants(self):
        for value in ['iwrawww','@iwrawww','t.me/iwrawww','https://t.me/iwrawww']:
            self.assertEqual(normalize_contact(value),('https://t.me/iwrawww','telegram'))
    def test_phone_variants(self):
        for value in ['+79961234567','79961234567','89961234567','7(996)1234567',
                      '+7 (996) 123-45-67','8 (996) 123-45-67','9961234567']:
            self.assertEqual(normalize_contact(value),('+79961234567','phone'))
    def test_incomplete_phone_and_unsafe_url(self):
        for value,kind in [('+7996',None),('7(996)',None),('javascript:alert(1)','telegram'),
                           ('https://t.me.evil/user','telegram'),('https://user@t.me/name','telegram')]:
            with self.subTest(value=value),self.assertRaises(ValueError):normalize_contact(value,kind)
    def test_legacy_unknown_contact_keeps_text_without_destination(self):
        self.assertEqual(normalize_contact('Спросить продавца'),('Спросить продавца',None))
    def test_city_prefix_and_alias(self):
        self.assertTrue({'Кемь','Кемерово'}.issubset({c['name'] for c in search_cities('Кем')}))
        self.assertEqual(search_cities('спб')[0]['city_id'],'ru:saint-petersburg')
    def test_namesakes_and_unique_ids(self):
        self.assertEqual(len(search_cities('Советск')),3)
        self.assertEqual(len({c['city_id'] for c in CITIES}),len(CITIES))

    def test_legacy_short_contact_is_not_made_into_invalid_telegram_link(self):
        self.assertEqual(normalize_contact('@test'),('@test',None))
        with self.assertRaises(ValueError):normalize_contact('@test','telegram')
