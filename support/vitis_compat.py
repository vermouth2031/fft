"""Run the unchanged software builder with a local Vitis server-output adapter."""
import importlib
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'build/logs'


class ServerOutput:
    """Keep raw diagnostics and return the UTF-8 bytes expected by AMD's reader."""

    def __init__(self, stream, process):
        self.stream = stream
        self.process = process

    def convert(self, raw):
        if not raw:
            return raw
        with (LOGS / 'vitis_server_stdout.raw.log').open('ab') as output:
            output.write(raw)
        try:
            decoded = raw.decode('utf-8', errors='strict')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            # Windows cmd.exe diagnostics use the local Chinese code page.
            # Strict decoding preserves errors; invalid data still raises.
            decoded = raw.decode('cp936', errors='strict')
            encoding = 'cp936'
        with (LOGS / 'vitis_server_stdout.utf8.log').open('a', encoding='utf-8') as output:
            output.write(decoded)
        if encoding == 'cp936':
            print('VITIS_SERVER_OUTPUT_CP936_ADAPTED: ' + decoded.rstrip(), flush=True)
        return decoded.encode('utf-8', errors='strict')

    def readline(self, *args, **kwargs):
        raw = self.stream.readline(*args, **kwargs)
        if raw == b'':
            # AMD's iter(readline, '') uses a text sentinel on a binary stream.
            # Refuse EOF instead of looping forever after a failed server start.
            raise RuntimeError('Vitis server output ended before its startup port was read; '
                               f'exit_code={self.process.poll()}. '
                               'See build/logs/vitis_server_stdout.raw.log and .utf8.log.')
        return self.convert(raw)

    def read(self, *args, **kwargs):
        return self.convert(self.stream.read(*args, **kwargs))

    def __getattr__(self, name):
        return getattr(self.stream, name)


class ServerSubprocess:
    """Proxy only vitis._server's subprocess reference, never the global module."""

    def __init__(self, original):
        self.original = original

    def Popen(self, *args, **kwargs):
        command = args[0] if args else kwargs.get('args', '')
        text = command if isinstance(command, str) else ' '.join(map(str, command))
        process = self.original.Popen(*args, **kwargs)
        if 'vitis-server.bat' in text.lower() and process.stdout is not None:
            with (LOGS / 'vitis_server_command.log').open('a', encoding='utf-8') as output:
                output.write(text + '\n')
            process.stdout = ServerOutput(process.stdout, process)
        return process

    def __getattr__(self, name):
        return getattr(self.original, name)


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    for name in ('vitis_server_stdout.raw.log', 'vitis_server_stdout.utf8.log', 'vitis_server_command.log'):
        (LOGS / name).write_bytes(b'')
    # Vitis -s supplies its supported CLI/protobuf/Python paths.
    server_module = importlib.import_module('vitis._server')
    server_module.subprocess = ServerSubprocess(server_module.subprocess)
    print('VITIS_LOCAL_STDOUT_ADAPTER_READY', flush=True)
    runpy.run_path(str(ROOT / 'scripts/build_software.py'), run_name='__main__')


if __name__ == '__main__':
    main()
