import unittest
from netvideo_view import mjpeg_variant_path


class VariantPaths(unittest.TestCase):
    def test_sibling_profiles_follow_current_source(self):
        source = r'C:\Video Folder\address-mjpeg-40k-1024x608-12fps.mjpeg'
        for limit in (30, 40, 45, 50, 55, 60):
            self.assertEqual(mjpeg_variant_path(source, limit),
                             source.replace('40k-', f'{limit}k-'))

    def test_unrelated_sources_and_invalid_limits_are_rejected(self):
        with self.assertRaises(ValueError): mjpeg_variant_path('other.mjpeg', 45)
        with self.assertRaises(ValueError): mjpeg_variant_path('other.mjpeg', 41)


if __name__ == '__main__': unittest.main()
