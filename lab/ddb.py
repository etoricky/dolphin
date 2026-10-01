# -*- coding: utf-8 -*-
"""DolphinDB session utilities: connect / session reuse (optional inject .dos formulas) / run script files / print small results.

"inject" = read the client-local .dos, strip the `module` declaration line, then use run() to
send the function definitions to the server and compile them into the current session
(no longer relying on the server-side moduleDir `use`).
"""
import os
import re
import sys

import dolphindb as ddb

import config

# Matches a declaration line like `module gtja191Alpha` (requires the whole line to be just module + one word)
_MODULE_DECL = re.compile(r'(?m)^\s*module\s+\S+\s*$')


def _read_module(dos_module):
    """Read a single .dos source and strip the `module xxx` declaration line."""
    with open(dos_module, "r", encoding="utf-8") as f:
        src = f.read()
    return _MODULE_DECL.sub("", src)


def load_modules(sess, dos_modules):
    """Inject the several .dos specified by dos_modules into the server session for sess, returning the number of injected characters.

    dos_modules are full paths of module files, ordered by dependency.
    """
    parts = []
    for path in dos_modules:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        parts.append(_read_module(path))

    script = "\n".join(parts)

    # Fallback: for uncleaned original files, strip the `moduleName::` namespace prefix (module name = file name minus .dos)
    for path in dos_modules:
        name = os.path.splitext(os.path.basename(path))[0]
        script = script.replace(name + "::", "")

    sess.run(script)
    return len(script)


def connect():
    """Establish and return a DolphinDB session."""
    s = ddb.session()
    s.connect(config.ddb_host, config.ddb_port, config.ddb_username, config.ddb_password)
    return s


_sessions = {}


def get_session(dos_modules=[]):
    """Establish / reuse a session by "the module files to inject".

    dos_modules=[]           -> base session (inject no formulas; used by upload / backtest01 / backtest02 / plot)
    dos_modules=[path, ...]  -> inject only the formulas of these .dos; each distinct file combination gets its own session, mutually invisible
    """
    key = tuple(dos_modules)
    if key not in _sessions:
        sess = connect()
        tag = "base" if not dos_modules else f"{len(dos_modules)} modules"
        print(f"connected to {config.ddb_host}:{config.ddb_port} (admin) [{tag}]")
        if dos_modules:
            try:
                n = load_modules(sess, dos_modules)
                print(f"injected modules {list(dos_modules)} ({n} chars)")
            except FileNotFoundError as e:
                print(f"[warn] module missing, skipping injection: {e}")
        _sessions[key] = sess
    return _sessions[key]


def run_file(s, path, preamble=""):
    """Run a DolphinDB script file (.dos); path is an absolute path.

    preamble is prepended to the script, used to pass runtime parameters (the script uses defined() for default-value protection).
    The script is self-contained (contains login / use module internally), so it can be run either with this function
    or opened and run directly in the VS Code DolphinDB plugin.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        script = f.read()
    print(f"\n===== running {path} =====")
    return s.run(preamble + script)


def show(obj, title=None):
    if title:
        print(f"\n----- {title} -----")
    print(obj)
    return obj


if __name__ == "__main__":
    sess = connect()
    print("connected to", config.ddb_host, config.ddb_port)
    print("version:", sess.run("version()"))
    print("homeDir:", sess.run("getHomeDir()"))
