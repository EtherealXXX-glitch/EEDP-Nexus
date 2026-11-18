import unittest
from wave_cache import WaveCache


class WaveCacheTest(unittest.TestCase):
    def data(self,start=0,count=1000,step=1):
        return dict(input="sample.sr",total_samples=1000,samplerate=1000000,start_sample=start,
            sample_count=count,bin_samples=step,exact=step==1,
            channels=[dict(name="D0",ranges=[[i%2,i%2] for i in range((count+step-1)//step)])])

    def test_exact_file_pans_and_zooms_without_fetch(self):
        cache=WaveCache()
        cache.add(self.data())
        for start,count in ((10,200),(500,100),(0,1000)):
            view,enough=cache.window(start,count,1200)
            self.assertTrue(enough)
            self.assertEqual(view["start_sample"],start)
            self.assertEqual(len(view["channels"][0]["ranges"]),count)

    def test_overview_immediately_covers_a_new_window_while_fine_data_arrives(self):
        cache=WaveCache()
        cache.add(self.data(step=10))
        view,enough=cache.window(203,101,800)
        self.assertIsNotNone(view)
        self.assertFalse(enough)
        self.assertEqual(view["bucket_start_sample"],200)
        cache.add(self.data(start=200,count=200,step=1))
        view,enough=cache.window(203,101,800)
        self.assertTrue(enough)
        self.assertEqual(view["bucket_start_sample"],203)

    def test_cache_memory_is_bounded_and_retains_overview(self):
        cache=WaveCache(limit=3)
        cache.add(self.data(step=10))
        for index in range(10):cache.add(self.data(start=index*10,count=20))
        self.assertEqual(len(cache.views),3)
        self.assertIsNotNone(cache.window(700,200,800)[0])
