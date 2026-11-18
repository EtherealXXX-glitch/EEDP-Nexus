"""Project TCP video v1 wire primitives; no network or hardware side effects."""
import struct

MAX_PAYLOAD = 61440
MJPEG_HEADER = struct.Struct('>4sIII')
H264_HEADER = struct.Struct('>4sIIIQ')


def annexb_types(payload):
    """Recognize Annex B start codes; this does not split access units."""
    import re
    starts = list(re.finditer(b'\x00\x00(?:\x00)?\x01', payload))
    if not starts or starts[0].start() != 0:
        raise ValueError('Expected Annex B start code')
    types = []
    for i, start in enumerate(starts):
        end = starts[i+1].start() if i+1 < len(starts) else len(payload)
        if start.end() >= end: raise ValueError('Empty NAL unit')
        header = payload[start.end()]
        if header & 0x80: raise ValueError('Invalid NAL forbidden bit')
        types.append(header & 31)
    return types


def packet(codec, payload, sequence, timestamp_us=0, first=False):
    if not 1 <= len(payload) <= MAX_PAYLOAD: raise ValueError('Payload size out of bounds')
    if type(sequence) is not int or not 1 <= sequence <= 0xffffffff:
        raise ValueError('Sequence out of bounds')
    if codec == 'mjpeg':
        if not payload.startswith(b'\xff\xd8') or not payload.endswith(b'\xff\xd9'):
            raise ValueError('Expected a complete JPEG without AVI padding')
        return MJPEG_HEADER.pack(b'MJPG',len(payload),sequence,0) + payload
    if codec != 'h264': raise ValueError('Unknown codec')
    if type(timestamp_us) is not int or not 0 <= timestamp_us <= 0xffffffffffffffff:
        raise ValueError('Timestamp out of bounds')
    types = annexb_types(payload)
    if not any(t in (1,5) for t in types): raise ValueError('Access unit lacks a picture')
    if first and not {7,8,5}.issubset(types):
        raise ValueError('Connection must start with SPS/PPS and IDR')
    return H264_HEADER.pack(b'H264',len(payload),sequence,int(5 in types),timestamp_us) + payload
