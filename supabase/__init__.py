"""
Shim to re-export from the real supabase package.

This directory is the Supabase CLI project (config, migrations) and shadows
the pip-installed 'supabase' package. We load the real package and re-export.
"""
import importlib.util
import sys
from pathlib import Path

# Find the real supabase package in site-packages
_this_dir = Path(__file__).resolve().parent
_real_init = None
for p in sys.path:
    if "site-packages" in p:
        fp = Path(p) / "supabase" / "__init__.py"
        if fp.exists() and fp.resolve() != Path(__file__).resolve():
            _real_init = fp
            _real_pkg_path = str(fp.parent)
            break

if _real_init is None:
    raise ImportError(
        "Could not find the supabase package. Install it with: pip install supabase"
    )

# Create a module for "supabase" with the real package path, load it
_real_module = type(sys)("supabase")
_real_module.__path__ = [_real_pkg_path]
_real_module.__package__ = "supabase"

# Temporarily replace ourselves so the real package's internal imports work
_old = sys.modules.get("supabase")
sys.modules["supabase"] = _real_module

try:
    spec = importlib.util.spec_from_file_location(
        "supabase", _real_init, submodule_search_locations=[_real_pkg_path]
    )
    spec.loader.exec_module(_real_module)
finally:
    if _old is not None:
        sys.modules["supabase"] = _old

# Re-export into this module's namespace
globals().update({k: getattr(_real_module, k) for k in dir(_real_module) if not k.startswith("_")})
__all__ = getattr(_real_module, "__all__", ())
