"""Keep source windows separate; portable executables use Windows' native identity."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import uuid

from app_paths import FROZEN
PRODUCTION_APP_ID='EEDP.Nexus.Workbench'
# The frozen executable already has its own path and embedded icon. Explicit
# window IDs can select an old Shell shortcut/group with a blank cached icon.
APP_ID=None if FROZEN else 'EEDP.Nexus.Development'


class GUID(ctypes.Structure):
    _fields_=[('data',ctypes.c_ubyte*16)]
    def __init__(self,value):super().__init__((ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(value).bytes_le))


class PROPERTYKEY(ctypes.Structure):
    _fields_=[('fmtid',GUID),('pid',wintypes.DWORD)]


class Value(ctypes.Union):
    _fields_=[('text',ctypes.c_wchar_p),('raw',ctypes.c_ubyte*(16 if ctypes.sizeof(ctypes.c_void_p)==8 else 8))]


class PROPVARIANT(ctypes.Structure):
    _anonymous_=('value',)
    _fields_=[('vt',wintypes.WORD),('r1',wintypes.WORD),('r2',wintypes.WORD),('r3',wintypes.WORD),('value',Value)]


IID=GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
FORMAT='9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'


def check(result):
    if result<0:raise OSError(f'Windows Shell identity failed: HRESULT 0x{result&0xffffffff:08x}')


def set_process_identity():
    if APP_ID is None:return
    shell=ctypes.WinDLL('shell32')
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes=[wintypes.LPCWSTR]
    shell.SetCurrentProcessExplicitAppUserModelID.restype=ctypes.c_long
    check(shell.SetCurrentProcessExplicitAppUserModelID(APP_ID))


class PropertyStore:
    def __init__(self,window=None,shortcut=None):
        self.pointer=ctypes.c_void_p()
        self.ole=ctypes.WinDLL('ole32')
        self.ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD]
        self.ole.CoInitializeEx.restype=ctypes.c_long
        initialized=self.ole.CoInitializeEx(None,2)
        self.initialized=initialized in (0,1)
        if initialized<0 and initialized!=-2147417850:check(initialized)
        shell=ctypes.WinDLL('shell32')
        if window is not None:
            fn=shell.SHGetPropertyStoreForWindow
            fn.argtypes=[wintypes.HWND,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
            fn.restype=ctypes.c_long
            check(fn(window,ctypes.byref(IID),ctypes.byref(self.pointer)))
        else:
            fn=shell.SHGetPropertyStoreFromParsingName
            fn.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
            fn.restype=ctypes.c_long
            check(fn(str(Path(shortcut).resolve()),None,2,ctypes.byref(IID),ctypes.byref(self.pointer)))
        self.table=ctypes.cast(self.pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

    def method(self,index,restype,*arguments):
        return ctypes.WINFUNCTYPE(restype,ctypes.c_void_p,*arguments)(self.table[index])

    def set(self,pid,text):
        key=PROPERTYKEY(GUID(FORMAT),pid)
        value=PROPVARIANT()
        if text is not None:
            buffer=ctypes.create_unicode_buffer(text)
            value.vt=31;value.text=ctypes.cast(buffer,ctypes.c_wchar_p)
        check(self.method(6,ctypes.c_long,ctypes.POINTER(PROPERTYKEY),ctypes.POINTER(PROPVARIANT))(self.pointer,ctypes.byref(key),ctypes.byref(value)))

    def get(self,pid):
        key=PROPERTYKEY(GUID(FORMAT),pid);value=PROPVARIANT()
        check(self.method(5,ctypes.c_long,ctypes.POINTER(PROPERTYKEY),ctypes.POINTER(PROPVARIANT))(self.pointer,ctypes.byref(key),ctypes.byref(value)))
        try:return value.text if value.vt==31 else None
        finally:
            clear=ctypes.WinDLL('ole32').PropVariantClear
            clear.argtypes=[ctypes.POINTER(PROPVARIANT)]
            clear(ctypes.byref(value))

    def commit(self):check(self.method(7,ctypes.c_long)(self.pointer))
    def close(self):
        if self.pointer:
            self.method(2,wintypes.ULONG)(self.pointer)
            self.pointer=None
        if self.initialized:
            self.ole.CoUninitialize()
            self.initialized=False


def set_window_identity(handle,icon):
    if APP_ID is None:return
    store=PropertyStore(window=handle)
    try:
        # Development only: avoid grouping source windows with other Python apps.
        for pid,text in ((2,None),(3,None),(4,None),(5,APP_ID)):
            store.set(pid,text)
        store.commit()
    finally:store.close()


def set_shortcut_identity(path):
    """Migrate legacy explicit IDs to the executable's standard Shell identity."""
    store=PropertyStore(shortcut=path)
    try:
        for pid in (2,3,4,5):store.set(pid,None)
        store.commit()
    finally:store.close()


def clear_window_identity(handle):
    if APP_ID is None:return
    store=PropertyStore(window=handle)
    try:
        for pid in (2,3,4,5):store.set(pid,None)
    finally:store.close()


if __name__=='__main__':
    set_shortcut_identity(sys.argv[1])
