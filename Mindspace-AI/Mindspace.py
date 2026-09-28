#MenuTitle: Mindspace
# -*- coding: utf-8 -*-
"""Mindspace — loader.

Skrip ini SENGAJA kecil dan jarang berubah. Setiap kali dijalankan dari
Glyphs Scripts menu, dia mengambil kode Mindspace yang sebenarnya (terbaru)
langsung dari server lalu menjalankannya — jadi tak pernah ketinggalan versi
lagi, lepas dari OneDrive/symlink/sync.

Setup sekali per Mac: file ~/.mindspace/awal_config.json berisi
{"server_url": "...", "api_key": "..."}.
"""

import os
import json
import hashlib
import ssl
import urllib.request
import urllib.error

_HOME = os.path.expanduser("~/.mindspace")
_CONFIG_PATH = os.path.join(_HOME, "awal_config.json")
_CACHE_PATH = os.path.join(_HOME, "Mindspace_cached.py")
_SCRIPT_NAME = "mindspace"
_FETCH_TIMEOUT = 10


def _ssl_context():
    # GlyphsApp's bundled Python.framework has no working default CA bundle —
    # point at macOS's own cert store instead (always present).
    for candidate in ("/etc/ssl/cert.pem",):
        if os.path.exists(candidate):
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


def _message(title, text):
    try:
        from GlyphsApp import Message
        Message(text, title)
    except Exception:
        print("[Mindspace] %s: %s" % (title, text))


def _load_config():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_json(url, api_key):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "User-Agent": "Mindspace-Glyphs-Loader/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=_ssl_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_version(server_url, api_key):
    data = _get_json(
        "%s/v1/client/script/version?name=%s" % (server_url, _SCRIPT_NAME), api_key
    )
    return data["sha256"]


def _fetch_latest(server_url, api_key):
    return _get_json(
        "%s/v1/client/script?name=%s" % (server_url, _SCRIPT_NAME), api_key
    )


def _local_cache_sha256():
    if not os.path.exists(_CACHE_PATH):
        return None
    with open(_CACHE_PATH, "r", encoding="utf-8") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()


def _clear_own_pycache():
    # If Glyphs ever loads this stub via an import path (observed for
    # scripts nested in a Scripts subfolder) it can leave a stale compiled
    # __pycache__ next to it that outlives edits to this .py source. Wipe
    # it defensively every run so a future edit can never get stuck behind
    # bytecode from before the edit.
    try:
        stub_dir = os.path.dirname(os.path.abspath(__file__))
        pycache = os.path.join(stub_dir, "__pycache__")
        if os.path.isdir(pycache):
            import shutil
            shutil.rmtree(pycache, ignore_errors=True)
    except Exception:
        pass


def _run():
    _clear_own_pycache()
    try:
        cfg = _load_config()
        server_url = cfg["server_url"]
        api_key = cfg["api_key"]
    except (OSError, ValueError, KeyError):
        _message(
            "Mindspace — belum di-setup",
            "Tidak ketemu/rusak: %s\n\nBuat file itu berisi:\n"
            '{"server_url": "http://...", "api_key": "..."}' % _CONFIG_PATH,
        )
        return

    source = None
    warning = None
    local_sha = _local_cache_sha256()
    try:
        if local_sha is not None and _fetch_version(server_url, api_key) == local_sha:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                source = f.read()
        else:
            data = _fetch_latest(server_url, api_key)
            source = data["content"]
            os.makedirs(_HOME, exist_ok=True)
            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                f.write(source)
    except urllib.error.HTTPError as e:
        warning = "HTTP %s: %s" % (e.code, e.read().decode(errors="replace"))
    except urllib.error.URLError as e:
        warning = "Tidak bisa terhubung ke %s: %s" % (server_url, e.reason)
    except Exception as e:
        warning = str(e)

    if source is None:
        if local_sha is not None:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                source = f.read()
            print("[Mindspace] Tidak bisa update (%s) — pakai cache lokal." % warning)
        else:
            _message("Mindspace — tidak bisa mengambil script", warning or "unknown error")
            return

    # GlyphsApp injects Glyphs/Message/vanilla/etc. into the real __main__
    # module (this stub, since Glyphs runs it as __main__) — start from a
    # copy of that dict so the payload inherits them, instead of a bare
    # dict where every GlyphsApp name is a NameError.
    import __main__ as _real_main
    g = dict(vars(_real_main))
    g["__name__"] = "__main__"
    g["__file__"] = _CACHE_PATH
    exec(compile(source, _CACHE_PATH, "exec"), g)


_run()
