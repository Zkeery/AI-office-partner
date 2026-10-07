"""One backend owns a data directory, including startup recovery and maintenance."""
from contextlib import contextmanager
from pathlib import Path
import os


@contextmanager
def data_lock(data_path: Path):
    data_path.mkdir(parents=True, exist_ok=True)
    handle = (data_path / ".service.lock").open("a+b")
    locked = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if not handle.read(1):
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise RuntimeError("数据目录正在使用；请停止现有服务后再启动或备份。后端仅支持单进程。") from exc
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
