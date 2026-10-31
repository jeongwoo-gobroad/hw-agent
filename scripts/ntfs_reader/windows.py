"""Bounded reads with native NTFS identity and reparse checks."""
import ctypes as C
from ctypes import wintypes as W
import ntpath


class FileInfo(C.Structure):
    _fields_ = [('attributes', W.DWORD), ('created', W.FILETIME), ('accessed', W.FILETIME),
                ('written', W.FILETIME), ('volume', W.DWORD), ('size_high', W.DWORD),
                ('size_low', W.DWORD), ('links', W.DWORD), ('id_high', W.DWORD), ('id_low', W.DWORD)]


class NativeReader:
    def __init__(self, root, serial, allowed, active):
        self.root = ntpath.normpath(root).rstrip('\\') + '\\'
        self.serial = int(serial, 16)
        self.allowed, self.active = allowed, active
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        def api(name, result, arguments):
            method = getattr(self.kernel, name)
            method.restype, method.argtypes = result, arguments
            return method
        self.create = api('CreateFileW', W.HANDLE, [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE])
        self.close = api('CloseHandle', W.BOOL, [W.HANDLE])
        self.info = api('GetFileInformationByHandle', W.BOOL, [W.HANDLE,C.POINTER(FileInfo)])
        self.final = api('GetFinalPathNameByHandleW', W.DWORD, [W.HANDLE,W.LPWSTR,W.DWORD,W.DWORD])
        self.ioctl = api('DeviceIoControl', W.BOOL, [W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p])
        self.seek = api('SetFilePointerEx', W.BOOL, [W.HANDLE,C.c_longlong,C.c_void_p,W.DWORD])
        self.read = api('ReadFile', W.BOOL, [W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p])

    def open(self, path, access=0):
        # 읽는 동안에도 Windows의 변환과 분리를 독점 잠금으로 막지 않는다.
        handle = self.create(path, access, 7, None, 3, 0x02200000, None)
        if handle == C.c_void_p(-1).value:
            raise OSError('File unavailable')
        return handle

    def information(self, handle):
        info = FileInfo()
        if not self.info(handle, C.byref(info)):
            raise OSError('File unavailable')
        return info

    def chunk(self, entry, offset, count):
        if not self.active() or self.allowed(entry['path']) is None:
            raise OSError('Reader closed')
        parent = ntpath.dirname(entry['path'])
        parents = []
        while len(parent) >= len(self.root.rstrip('\\')):
            parents.append(parent)
            next_parent = ntpath.dirname(parent)
            if next_parent == parent:
                break
            parent = next_parent
        for parent in reversed(parents):
            handle = self.open(parent)
            try:
                if self.information(handle).attributes & 0x400:
                    raise OSError('Reparse path denied')
            finally:
                self.close(handle)
        handle = self.open(entry['path'], 0x80000000 if count else 0)
        try:
            info = self.information(handle)
            if (info.attributes & (0x400 | 0x10) or info.links != 1 or info.volume != self.serial
                    or str((info.id_high << 32) | info.id_low) != entry['identity']
                    or ((info.size_high << 32) | info.size_low) != entry['size']):
                raise OSError('File identity changed')
            buffer = C.create_unicode_buffer(32768)
            flags = 1 if self.root.startswith('\\\\?\\Volume{') else 0
            length = self.final(handle, buffer, len(buffer), flags)
            expected = entry['path'] if entry['path'].startswith('\\\\?\\') else '\\\\?\\' + entry['path']
            if not length or length >= len(buffer) or buffer.value.casefold() != expected.casefold():
                raise OSError('Resolved path changed')
            compression, returned = W.USHORT(), W.DWORD()
            if not self.ioctl(handle, 0x9003C, None, 0, C.byref(compression), 2, C.byref(returned), None) or compression.value:
                raise OSError('File is not ready')
            if not self.active():
                raise OSError('Reader closed')
            if not count:
                return b''
            data = C.create_string_buffer(count)
            if not self.seek(handle, offset, None, 0) or not self.read(handle, data, count, C.byref(returned), None):
                raise OSError('Read unavailable')
            return data.raw[:returned.value]
        finally:
            # 네트워크 전송을 기다리는 동안 원본 파일 핸들을 잡지 않는다.
            self.close(handle)
