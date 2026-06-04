"""Wrapper to start kiro-gateway with SSL verification disabled (for corporate VPN/TLS inspection)."""
import httpx

_orig_init = httpx.AsyncClient.__init__

def _patched_init(self, *args, **kwargs):
    kwargs.setdefault('verify', False)
    _orig_init(self, *args, **kwargs)

httpx.AsyncClient.__init__ = _patched_init

import runpy
runpy.run_path('main.py', run_name='__main__')
