"""Verify vendor discovery + offline UART decoding. Never starts hardware acquisition."""
import json
from pathlib import Path
import zipfile

from core import Activity, Resources
from plugins.slogic.component import SLogic


def main():
    root=Path(__file__).parent/"build/slogic-offline-check"
    root.mkdir(parents=True,exist_ok=True)
    component=SLogic(Activity(root/"logs"),Resources())
    try:
        devices=component.devices()
        capabilities=component.capabilities()
        plan=component.inspect()
        component.decoder("uart")
        # Synthetic UART 100000 baud, 8N1, sampled at 1MHz; not data from the device.
        values=[1]*100
        for character in b"OK\n":
            for bit in [0,*[(character>>shift)&1 for shift in range(8)],1,1]: values.extend([bit]*10)
        values.extend([1]*100)
        sample=root/"synthetic-uart-100000.sr"
        with zipfile.ZipFile(sample,"w",zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("version","2")
            archive.writestr("metadata","[global]\nsigrok version=0.6.0\n\n[device 1]\ncapturefile=logic-1\ntotal probes=1\nsamplerate=1 MHz\nunitsize=1\nprobe1=D0\n")
            archive.writestr("logic-1-1",bytes(values))
        waveform=component.waveform(str(sample),pixels=1000)
        assert waveform["total_samples"]==len(values)
        component.decode(str(sample),"uart:rx=D0:baudrate=100000:format=ascii")
        component.worker.join(30)
        decoded=component.status()
        assert decoded["state"]=="succeeded",decoded
        assert decoded["annotations"],decoded
        assert "O" in decoded["preview"] and "K" in decoded["preview"],decoded
        component.export(str(sample),"vcd")
        component.worker.join(30)
        exported=component.status()
        assert exported["state"]=="succeeded",exported
        print(json.dumps(dict(devices=devices["devices"],channels=capabilities["channels"],
            samplerates=capabilities["samplerates"],preflight_only=plan["estimated_samples"],
            synthetic_samples=len(values),decoded_preview=decoded["preview"],waveform=True,
            export=exported["output"],hardware_capture=False),ensure_ascii=True))
    finally:
        component.close()
        component.activity.close()


if __name__=="__main__":main()
