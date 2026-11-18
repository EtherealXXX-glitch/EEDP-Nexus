import unittest
from nexus_ui.receive_display import preview

class ReceiveDisplayTests(unittest.TestCase):
    def test_binary_flood_is_compact(self):
        self.assertEqual(preview('\0'*1000000),'[00 × 1000000]')

    def test_long_line_is_bounded(self):
        value=preview('a'*1000000)
        self.assertIn('完整数据见日志',value)
        self.assertLess(len(value),4200)
        self.assertLessEqual(max(map(len,value.splitlines())),256)

    def test_normal_logs_unchanged(self):
        self.assertEqual(preview('hello\nworld\n'),'hello\nworld\n')
