"""Bounded, display-only serial formatting. Raw events are never modified."""
import re
import textwrap

MAX_EVENT = 4096
MAX_VIEW = 100_000


def preview(text):
    text = re.sub(r'\x00{8,}', lambda match: f'[00 × {len(match[0])}]', text)
    text = text.replace('\x00', '␀')
    if len(text) > MAX_EVENT:
        text = '[显示省略，完整数据见日志]\n' + text[-MAX_EVENT:]
    # Actual short logical lines avoid Tk's quadratic layout of unbroken streams.
    return '\n'.join('\n'.join(line[i:i+256] for i in range(0,len(line),256))
                     for line in text.split('\n'))
