import subprocess
import sys

from streamlink.stream.stream import Stream, StreamIO


class ProcessStreamIO(StreamIO):
    def __init__(self, command):
        super().__init__()
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def readable(self):
        return True

    def read(self, size=-1):
        return self.process.stdout.read(size)

    def close(self):
        if self.closed:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.process.stdout:
            self.process.stdout.close()
        super().close()


class ProcessStream(Stream):
    __shortname__ = "process"

    def __init__(self, session, module, *arguments):
        super().__init__(session)
        self.command = [sys.executable, "-m", module, "--capture", *arguments]

    def open(self):
        return ProcessStreamIO(self.command)
