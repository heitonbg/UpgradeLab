"""Deterministic checks for strict FPS cohort aggregation."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.benchmark_aggregation import aggregate


def run(identifier, fps, publisher='A', series='one', **changes):
    row=dict(id=identifier, game='CS2', game_version='1', cpu='Ryzen 5 5600',
             gpu='RTX 3060', ram_gb=16, ram_type='DDR4', ram_channels=2,
             resolution='1080p', preset='Low', rt=False, upscaling='off',
             frame_generation=False, scene='benchmark', overclocked=False,
             os='Windows', form_factor='Desktop', average_fps=fps,
             publisher=publisher, series_id=series, source_url='https://example.org/benchmark',
             source_ids=[identifier], license='CC-BY-4.0', attribution='Example source')
    row.update(changes)
    return row


class AggregateTests(unittest.TestCase):
    def test_repeats_do_not_outvote_independent_series(self):
        rows=[run(str(i), 500, series='repeated') for i in range(1000)]
        rows += [run('other'+str(i), 100, publisher='B', series='independent'+str(i)) for i in range(5)]
        result=aggregate(rows)[0]
        self.assertAlmostEqual(result['mean_fps'], 300)
        self.assertEqual(result['independent_series'],6)
        self.assertEqual(result['independent_publishers'],2)
        self.assertEqual(result['observations'],1005)
        self.assertIsNone(result['one_percent_low_fps'])

    def test_one_publisher_with_many_series_cannot_dominate_five_publishers(self):
        rows=[run('a'+str(i),500,publisher='A',series='series'+str(i)) for i in range(100)]
        rows += [run('b'+str(i),100,publisher='P'+str(i),series='independent'+str(i)) for i in range(5)]
        value=aggregate(rows)[0]
        self.assertAlmostEqual(value['mean_fps'], (500+5*100)/6)
        self.assertEqual(value['independent_series'],105)
        self.assertEqual(value['independent_publishers'],6)

    def test_known_and_unknown_settings_are_separate(self):
        rows=[run('known',100),run('unknown',110,ram_channels=None),
              run('rt',70,rt=True),run('game',60,game='Dota 2')]
        self.assertEqual(len(aggregate(rows)),4)

    def test_estimates_are_excluded_and_invalid_rows_rejected(self):
        self.assertEqual(aggregate([run('estimate',100,data_type='estimated')]),[])
        with self.assertRaises(ValueError):aggregate([run('same',100),run('same',120)])
        with self.assertRaises(ValueError):aggregate([run('bad',-1)])


if __name__=='__main__':unittest.main()

