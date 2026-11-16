"""Offline MJPEG conversion helper, built with Pillow/libjpeg."""
import io
import json
from pathlib import Path
import sys
from PIL import Image

def main(source, target, target_quality=0, limit_kib=60):
    target_quality=int(target_quality)
    limit_kib=int(limit_kib)
    if target_quality != 0 and not 10 <= target_quality <= 95:raise ValueError('JPEG quality must be 0 or 10–95')
    if not 10 <= limit_kib <= 60:raise ValueError('JPEG limit must be 10–60 KiB')
    limit=limit_kib*1024
    data=Path(source).read_bytes()
    position=0; count=0; recompressed=0
    with open(target,'wb') as out:
        while position<len(data):
            end=data.find(b'\xff\xd9',position)
            if end<0 or data[position:position+2]!=b'\xff\xd8':raise ValueError('Invalid JPEG stream')
            with Image.open(io.BytesIO(data[position:end+2])) as image:
                if image.size!=(1024,608):raise ValueError('Unexpected JPEG size')
                image.load()
                rgb=image.convert('RGB')
                if target_quality == 0:
                    # 自动选择尽可能高的质量；每次都检验实际输出字节数。
                    lo, hi, frame, quality = 10, 95, None, 0
                    while lo <= hi:
                        q = (lo + hi) // 2
                        buffer=io.BytesIO(); rgb.save(buffer,format='JPEG',quality=q,subsampling=1)
                        trial=buffer.getvalue()
                        if len(trial)<=limit:frame,quality=trial,q;lo=q+1
                        else:hi=q-1
                    if frame is None:raise ValueError('JPEG exceeds the selected limit even at minimum quality')
                    if quality < 95:recompressed+=1
                else:
                    for quality in [target_quality, *[q for q in (85,70,55,40,25,10) if q < target_quality]]:
                        buffer=io.BytesIO()
                        rgb.save(buffer,format='JPEG',quality=quality,subsampling=1)
                        frame=buffer.getvalue()
                        if len(frame)<=limit:break
                    else:raise ValueError('JPEG exceeds the selected limit even at minimum quality')
                    if quality!=target_quality:recompressed+=1
                out.write(frame);count+=1
            position=end+2
    print(json.dumps(dict(frames=count,recompressed_frames=recompressed)))

if __name__=='__main__':main(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else 0,sys.argv[4] if len(sys.argv)>4 else 60)
