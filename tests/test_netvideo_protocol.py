import struct
import unittest
from nexus_core.netvideo_protocol import packet

class ProtocolTests(unittest.TestCase):
    def test_jpeg_wire_and_padding(self):
        payload=b'\xff\xd8abc\xff\xd9'
        value=packet('mjpeg',payload,1)
        self.assertEqual(struct.unpack('>4sIII',value[:16]),(b'MJPG',7,1,0))
        self.assertEqual(value[16:],payload)
        with self.assertRaises(ValueError):packet('mjpeg',payload+b'\0',1)

    def test_h264_first_frame_and_endian(self):
        payload=b'\0\0\0\1\x67a\0\0\1\x68b\0\0\1\x65c'
        value=packet('h264',payload,1,123456,first=True)
        self.assertEqual(struct.unpack('>4sIIIQ',value[:24]),(b'H264',len(payload),1,1,123456))
        with self.assertRaises(ValueError):packet('h264',b'\0\0\1\x41a',1,first=True)

    def test_size_limits(self):
        with self.assertRaises(ValueError):packet('mjpeg',b'a'*61441,1)
        with self.assertRaises(ValueError):packet('mjpeg',b'',1)
