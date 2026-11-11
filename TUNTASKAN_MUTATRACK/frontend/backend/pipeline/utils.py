import os
import shutil
import subprocess
import threading
from typing import Callable, List, Optional

class PipelineCancelledException(Exception):
    pass

class SubprocessRunner:
    def __init__(self):
        self.current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._cancelled = False

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                except Exception:
                    pass
                try:
                    self.current_process.kill()
                except Exception:
                    pass

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def run_cmd(
        self,
        cmd: List[str],
        log_callback: Callable[[str], None],
        cwd: Optional[str] = None,
        pipe_stdin_from: Optional[subprocess.Popen] = None,
        pipe_stdout_to_file: Optional[str] = None,
    ) -> subprocess.Popen:
        if self.is_cancelled():
            raise PipelineCancelledException("Operasi dibatalkan sebelum perintah dimulai.")

        cmd_str = " ".join(cmd)
        log_callback(f"$ {cmd_str}")

        stdout_dest = subprocess.PIPE
        file_handle = None
        if pipe_stdout_to_file:
            file_handle = open(pipe_stdout_to_file, "w")
            stdout_dest = file_handle

        stdin_source = pipe_stdin_from.stdout if pipe_stdin_from else None

        process = subprocess.Popen(
            cmd,
            stdin=stdin_source,
            stdout=stdout_dest,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        with self._lock:
            self.current_process = process

        if pipe_stdin_from and pipe_stdin_from.stdout:
            pipe_stdin_from.stdout.close()

        # Stream stderr in real time
        if process.stderr:
            for line in iter(process.stderr.readline, ''):
                if line:
                    clean_line = line.rstrip()
                    if clean_line:
                        log_callback(clean_line)
                if self.is_cancelled():
                    process.kill()
                    if file_handle:
                        file_handle.close()
                    raise PipelineCancelledException("Pipeline dibatalkan oleh pengguna.")

        # If stdout wasn't redirected to a file, read it too
        if stdout_dest == subprocess.PIPE and process.stdout:
            for line in iter(process.stdout.readline, ''):
                if line:
                    clean_line = line.rstrip()
                    if clean_line:
                        log_callback(clean_line)
                if self.is_cancelled():
                    process.kill()
                    raise PipelineCancelledException("Pipeline dibatalkan oleh pengguna.")

        return_code = process.wait()
        if file_handle:
            file_handle.close()

        with self._lock:
            self.current_process = None

        if self.is_cancelled():
            raise PipelineCancelledException("Pipeline dibatalkan oleh pengguna.")

        if return_code != 0:
            raise RuntimeError(f"Perintah '{cmd[0]}' gagal dengan exit code {return_code}.")

        return process

def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
