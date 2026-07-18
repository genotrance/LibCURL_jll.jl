"""Smoke tests for libcurl binaries using ctypes.

Exercises libcurl via ctypes against a local HTTP server: version checks,
feature flags, GET/POST, HTTPS, headers, redirects, multi interface, and
error handling. No pymcurl or external dependencies beyond pytest.
"""

import ctypes
import ctypes.util
import json
import os
import platform
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

# ---------------------------------------------------------------------------
# libcurl constants (from curl.h)
# ---------------------------------------------------------------------------
CURL_GLOBAL_DEFAULT = 3
CURLE_OK = 0

_OPT_LONG = 0
_OPT_OBJ = 10000
_OPT_FUNC = 20000

CURLOPT_URL = _OPT_OBJ + 2
CURLOPT_WRITEFUNCTION = _OPT_FUNC + 11
CURLOPT_USERAGENT = _OPT_OBJ + 18
CURLOPT_HTTPHEADER = _OPT_OBJ + 23
CURLOPT_POST = _OPT_LONG + 47
CURLOPT_POSTFIELDS = _OPT_OBJ + 15
CURLOPT_POSTFIELDSIZE = _OPT_LONG + 60
CURLOPT_FOLLOWLOCATION = _OPT_LONG + 52
CURLOPT_MAXREDIRS = _OPT_LONG + 68
CURLOPT_TIMEOUT = _OPT_LONG + 13
CURLOPT_CONNECTTIMEOUT = _OPT_LONG + 78
CURLOPT_SSL_VERIFYPEER = _OPT_LONG + 64
CURLOPT_SSL_VERIFYHOST = _OPT_LONG + 81
CURLOPT_CUSTOMREQUEST = _OPT_OBJ + 36
CURLOPT_NOBODY = _OPT_LONG + 44
CURLOPT_HEADERFUNCTION = _OPT_FUNC + 79
CURLOPT_CAINFO = _OPT_OBJ + 65

_INFO_STRING = 0x100000
_INFO_LONG = 0x200000
_INFO_DOUBLE = 0x300000
CURLINFO_RESPONSE_CODE = _INFO_LONG + 2
CURLINFO_EFFECTIVE_URL = _INFO_STRING + 1
CURLINFO_TOTAL_TIME = _INFO_DOUBLE + 3
CURLINFO_CONTENT_TYPE = _INFO_STRING + 18

CURL_VERSION_IPV6 = 1 << 0
CURL_VERSION_SSL = 1 << 2
CURL_VERSION_LIBZ = 1 << 3
CURL_VERSION_NTLM = 1 << 4
CURL_VERSION_SPNEGO = 1 << 8
CURL_VERSION_SSPI = 1 << 11
CURL_VERSION_HTTP2 = 1 << 16
CURL_VERSION_GSSAPI = 1 << 17
CURL_VERSION_KERBEROS5 = 1 << 18
CURL_VERSION_ZSTD = 1 << 26

WRITE_CB = ctypes.CFUNCTYPE(
    ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.c_size_t, ctypes.c_void_p,
)


class _VersionInfo(ctypes.Structure):
    _fields_ = [
        ("age", ctypes.c_int),
        ("version", ctypes.c_char_p),
        ("version_num", ctypes.c_uint),
        ("host", ctypes.c_char_p),
        ("features", ctypes.c_int),
        ("ssl_version", ctypes.c_char_p),
        ("ssl_version_num", ctypes.c_long),
        ("libz_version", ctypes.c_char_p),
        ("protocols", ctypes.POINTER(ctypes.c_char_p)),
    ]


# ---------------------------------------------------------------------------
# Load libcurl
# ---------------------------------------------------------------------------
def _find_libcurl():
    """Find and load libcurl shared library."""
    if sys.platform == "win32":
        names = ["libcurl.dll", "libcurl-4.dll", "curl.dll"]
    elif sys.platform == "darwin":
        names = ["libcurl.4.dylib", "libcurl.dylib"]
    else:
        names = ["libcurl.so.4", "libcurl.so"]

    # On Windows Python 3.8+, DLL search doesn't use PATH by default.
    # Register directories from PATH via os.add_dll_directory().
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        for d in os.environ.get("PATH", "").split(os.pathsep):
            d = d.strip()
            if d and os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass

    # Try direct names first (respects LD_LIBRARY_PATH / DYLD_LIBRARY_PATH)
    for name in names:
        try:
            return ctypes.CDLL(name)
        except OSError:
            pass

    # Fallback to ctypes.util
    path = ctypes.util.find_library("curl")
    if path:
        return ctypes.CDLL(path)

    pytest.skip("libcurl not found", allow_module_level=True)


lib = _find_libcurl()

# Set up function signatures for non-variadic functions
lib.curl_global_init.restype = ctypes.c_int
lib.curl_global_init.argtypes = [ctypes.c_long]
lib.curl_global_cleanup.restype = None
lib.curl_easy_init.restype = ctypes.c_void_p
lib.curl_easy_cleanup.restype = None
lib.curl_easy_cleanup.argtypes = [ctypes.c_void_p]
lib.curl_easy_perform.restype = ctypes.c_int
lib.curl_easy_perform.argtypes = [ctypes.c_void_p]
lib.curl_easy_reset.restype = None
lib.curl_easy_reset.argtypes = [ctypes.c_void_p]
lib.curl_version.restype = ctypes.c_char_p
lib.curl_version_info.restype = ctypes.POINTER(_VersionInfo)
lib.curl_version_info.argtypes = [ctypes.c_int]
lib.curl_easy_strerror.restype = ctypes.c_char_p
lib.curl_easy_strerror.argtypes = [ctypes.c_int]
lib.curl_slist_append.restype = ctypes.c_void_p
lib.curl_slist_append.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
lib.curl_slist_free_all.restype = None
lib.curl_slist_free_all.argtypes = [ctypes.c_void_p]
lib.curl_multi_init.restype = ctypes.c_void_p
lib.curl_multi_cleanup.restype = ctypes.c_int
lib.curl_multi_cleanup.argtypes = [ctypes.c_void_p]
lib.curl_multi_add_handle.restype = ctypes.c_int
lib.curl_multi_add_handle.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
lib.curl_multi_remove_handle.restype = ctypes.c_int
lib.curl_multi_remove_handle.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
lib.curl_multi_perform.restype = ctypes.c_int
lib.curl_multi_perform.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]

# curl_easy_setopt and curl_easy_getinfo are variadic C functions.
# Calling variadics through ctypes requires platform-specific handling:
#
# - x86_64 & Linux ARM64: variadic and non-variadic functions use the same
#   calling convention for integer/pointer args, so casting the function to a
#   fixed-signature CFUNCTYPE works.
#
# - macOS ARM64: the Apple ABI puts variadic args on the stack rather than in
#   registers. CFUNCTYPE creates non-variadic wrappers that put the 3rd arg in
#   x2, but curl_easy_setopt expects it on the stack. We use a small compiled C
#   helper (curl_helpers.c) that wraps the variadic calls into non-variadic ones.
_APPLE_ARM64 = sys.platform == "darwin" and platform.machine() == "arm64"

if _APPLE_ARM64:
    # Load the compiled C helper that wraps curl variadic functions.
    # It lives alongside libcurl in the library search path.
    _helpers = None
    _helper_dirs = []
    for var in ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
        for d in os.environ.get(var, "").split(":"):
            if d and os.path.isdir(d):
                _helper_dirs.append(d)
    _helper_dirs.append("/tmp/libcurl/lib")
    for _d in _helper_dirs:
        _p = os.path.join(_d, "libcurl_helpers.dylib")
        if os.path.isfile(_p):
            _helpers = ctypes.CDLL(_p)
            break
    if _helpers is None:
        pytest.skip("libcurl_helpers not found (required for macOS ARM64 variadic calls)",
                     allow_module_level=True)
    _helpers.curl_setopt_long.restype = ctypes.c_int
    _helpers.curl_setopt_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    _helpers.curl_setopt_str.restype = ctypes.c_int
    _helpers.curl_setopt_str.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
    _helpers.curl_setopt_ptr.restype = ctypes.c_int
    _helpers.curl_setopt_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    _helpers.curl_getinfo_ptr.restype = ctypes.c_int
    _helpers.curl_getinfo_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
else:
    # CFUNCTYPE wrappers: cast the variadic function to fixed-signature
    # non-variadic pointers (safe because int/ptr calling convention matches).
    _SETOPT_LONG = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_long)
    _SETOPT_STR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p)
    _SETOPT_PTR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
    _GETINFO_PTR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
    _setopt_long_cfn = _SETOPT_LONG(("curl_easy_setopt", lib))
    _setopt_str_cfn = _SETOPT_STR(("curl_easy_setopt", lib))
    _setopt_ptr_cfn = _SETOPT_PTR(("curl_easy_setopt", lib))
    _getinfo_cfn = _GETINFO_PTR(("curl_easy_getinfo", lib))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
if _APPLE_ARM64:
    def _setopt_long(easy, opt, val):
        _helpers.curl_setopt_long(easy, opt, val)

    def _setopt_str(easy, opt, val):
        _helpers.curl_setopt_str(easy, opt, val)

    def _setopt_ptr(easy, opt, val):
        _helpers.curl_setopt_ptr(easy, opt, val)

    def _getinfo_long(easy, info):
        val = ctypes.c_long()
        _helpers.curl_getinfo_ptr(easy, info, ctypes.byref(val))
        return val.value

    def _getinfo_str(easy, info):
        val = ctypes.c_char_p()
        _helpers.curl_getinfo_ptr(easy, info, ctypes.byref(val))
        return val.value.decode() if val.value else None

    def _getinfo_double(easy, info):
        val = ctypes.c_double()
        _helpers.curl_getinfo_ptr(easy, info, ctypes.byref(val))
        return val.value
else:
    def _setopt_long(easy, opt, val):
        _setopt_long_cfn(easy, opt, val)

    def _setopt_str(easy, opt, val):
        _setopt_str_cfn(easy, opt, val)

    def _setopt_ptr(easy, opt, val):
        _setopt_ptr_cfn(easy, opt, val)

    def _getinfo_long(easy, info):
        val = ctypes.c_long()
        _getinfo_cfn(easy, info, ctypes.byref(val))
        return val.value

    def _getinfo_str(easy, info):
        val = ctypes.c_char_p()
        _getinfo_cfn(easy, info, ctypes.byref(val))
        return val.value.decode() if val.value else None

    def _getinfo_double(easy, info):
        val = ctypes.c_double()
        _getinfo_cfn(easy, info, ctypes.byref(val))
        return val.value


def _make_write_cb(buf):
    """Return a ctypes write callback that appends to *buf* (a bytearray)."""
    @WRITE_CB
    def _cb(data, size, nmemb, _userdata):
        length = size * nmemb
        buf.extend(ctypes.string_at(data, length))
        return length
    return _cb


def _perform(url, *, method="GET", headers=None, data=None,
             follow=False, maxredirs=-1, timeout=15, insecure=False,
             nobody=False, connect_timeout=5):
    """High-level helper: perform a request and return (code, response_code, body, hdrs)."""
    easy = lib.curl_easy_init()
    assert easy, "curl_easy_init failed"

    body = bytearray()
    hdr_buf = bytearray()
    # Must keep references alive until after perform
    write_cb = _make_write_cb(body)
    header_cb = _make_write_cb(hdr_buf)
    # Keep ctypes objects alive so pointers stay valid
    _refs = []

    url_b = url.encode()
    _refs.append(url_b)
    _setopt_str(easy, CURLOPT_URL, url_b)
    _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, write_cb)
    _setopt_ptr(easy, CURLOPT_HEADERFUNCTION, header_cb)
    _setopt_long(easy, CURLOPT_TIMEOUT, timeout)
    _setopt_long(easy, CURLOPT_CONNECTTIMEOUT, connect_timeout)

    if method != "GET":
        method_b = method.encode()
        _refs.append(method_b)
        _setopt_str(easy, CURLOPT_CUSTOMREQUEST, method_b)
    if data is not None:
        data_b = data.encode() if isinstance(data, str) else data
        _refs.append(data_b)
        _setopt_long(easy, CURLOPT_POST, 1)
        _setopt_str(easy, CURLOPT_POSTFIELDS, data_b)
        _setopt_long(easy, CURLOPT_POSTFIELDSIZE, len(data_b))
    if follow:
        _setopt_long(easy, CURLOPT_FOLLOWLOCATION, 1)
        _setopt_long(easy, CURLOPT_MAXREDIRS, maxredirs)
    if insecure:
        _setopt_long(easy, CURLOPT_SSL_VERIFYPEER, 0)
        _setopt_long(easy, CURLOPT_SSL_VERIFYHOST, 0)
    if nobody:
        _setopt_long(easy, CURLOPT_NOBODY, 1)

    slist = None
    if headers:
        for h in headers:
            slist = lib.curl_slist_append(slist, h.encode())
        _setopt_ptr(easy, CURLOPT_HTTPHEADER, slist)

    code = lib.curl_easy_perform(easy)
    resp_code = _getinfo_long(easy, CURLINFO_RESPONSE_CODE) if code == CURLE_OK else 0

    if slist:
        lib.curl_slist_free_all(slist)
    lib.curl_easy_cleanup(easy)
    del _refs

    return code, resp_code, bytes(body), hdr_buf.decode(errors="replace")


# ---------------------------------------------------------------------------
# Local HTTP test server
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    """Minimal httpbin-like handler for tests."""

    def log_message(self, *_args):
        pass  # silence request logs

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/get":
            self._send_json({
                "url": self.path,
                "headers": dict(self.headers),
                "method": "GET",
            })
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://{self.headers['Host']}/get")
            self.end_headers()
        elif self.path == "/redirect/chain":
            self.send_response(302)
            self.send_header("Location", f"http://{self.headers['Host']}/redirect")
            self.end_headers()
        elif self.path == "/status/404":
            self.send_response(404)
            self.end_headers()
        elif self.path == "/status/500":
            self.send_response(500)
            self.end_headers()
        elif self.path == "/headers":
            self._send_json({"headers": dict(self.headers)})
        elif self.path == "/user-agent":
            self._send_json({"user-agent": self.headers.get("User-Agent", "")})
        elif self.path == "/delay":
            import time; time.sleep(3)
            self._send_json({"delayed": True})
        elif self.path == "/binary":
            data = bytes(range(256)) * 4
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

    def do_POST(self):
        body = self._read_body()
        self._send_json({
            "url": self.path,
            "method": "POST",
            "data": body.decode(errors="replace"),
            "headers": dict(self.headers),
        })

    def do_PUT(self):
        body = self._read_body()
        self._send_json({"method": "PUT", "data": body.decode(errors="replace")})

    def do_DELETE(self):
        self._send_json({"method": "DELETE"})

    def do_PATCH(self):
        body = self._read_body()
        self._send_json({"method": "PATCH", "data": body.decode(errors="replace")})

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("X-Head-Test", "present")
        self.end_headers()


@pytest.fixture(scope="module")
def server():
    """Start a local HTTP server for tests."""
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.fixture(scope="module", autouse=True)
def curl_global():
    """Initialize and clean up libcurl globally."""
    lib.curl_global_init(CURL_GLOBAL_DEFAULT)
    yield
    lib.curl_global_cleanup()


# ---------------------------------------------------------------------------
# Tests: version & features
# ---------------------------------------------------------------------------
class TestVersion:
    def test_curl_version_string(self):
        ver = lib.curl_version().decode()
        assert "libcurl" in ver

    def test_version_info(self):
        vi = lib.curl_version_info(0).contents
        assert vi.version_num > 0
        ver = vi.version.decode()
        assert len(ver) > 0

    def test_ssl_version(self):
        vi = lib.curl_version_info(0).contents
        ssl_ver = vi.ssl_version.decode() if vi.ssl_version else ""
        assert len(ssl_ver) > 0, "No SSL backend"

    def test_zlib_version(self):
        vi = lib.curl_version_info(0).contents
        assert vi.libz_version is not None

    def test_feature_ssl(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_SSL, "SSL not available"

    def test_feature_ipv6(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_IPV6, "IPv6 not available"

    def test_feature_libz(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_LIBZ, "zlib not available"

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows build may lack nghttp2 linkage")
    def test_feature_http2(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_HTTP2, "HTTP/2 not available"

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows build may lack zstd linkage")
    def test_feature_zstd(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_ZSTD, "zstd not available"

    def test_feature_ntlm(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_NTLM, "NTLM not available"

    @pytest.mark.skipif(sys.platform == "darwin", reason="macOS build lacks GSSAPI/SSPI for SPNEGO")
    def test_feature_spnego(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_SPNEGO, "SPNEGO not available"

    @pytest.mark.skipif(sys.platform == "darwin", reason="macOS build lacks GSSAPI/SSPI for Kerberos")
    def test_feature_kerberos5(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_KERBEROS5, "Kerberos5 not available"

    @pytest.mark.skipif(sys.platform != "linux", reason="GSSAPI only on Linux/FreeBSD (via Kerberos_krb5)")
    def test_feature_gssapi(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_GSSAPI, "GSSAPI not available"

    @pytest.mark.skipif(sys.platform != "win32", reason="SSPI only on Windows")
    def test_feature_sspi(self):
        vi = lib.curl_version_info(0).contents
        assert vi.features & CURL_VERSION_SSPI, "SSPI not available"

    def test_protocols(self):
        vi = lib.curl_version_info(0).contents
        protos = []
        i = 0
        while vi.protocols[i]:
            protos.append(vi.protocols[i].decode())
            i += 1
        assert "http" in protos
        assert "https" in protos

    def test_strerror(self):
        msg = lib.curl_easy_strerror(CURLE_OK).decode()
        assert len(msg) > 0


# ---------------------------------------------------------------------------
# Tests: easy interface lifecycle
# ---------------------------------------------------------------------------
class TestLifecycle:
    def test_init_cleanup(self):
        easy = lib.curl_easy_init()
        assert easy is not None and easy != 0
        lib.curl_easy_cleanup(easy)

    def test_reset(self):
        easy = lib.curl_easy_init()
        _setopt_str(easy, CURLOPT_URL, b"http://example.com")
        lib.curl_easy_reset(easy)
        lib.curl_easy_cleanup(easy)

    def test_slist(self):
        slist = lib.curl_slist_append(None, b"X-Test: value1")
        assert slist is not None
        slist = lib.curl_slist_append(slist, b"X-Test2: value2")
        lib.curl_slist_free_all(slist)


# ---------------------------------------------------------------------------
# Tests: HTTP GET
# ---------------------------------------------------------------------------
class TestGet:
    def test_basic_get(self, server):
        code, resp, body, _ = _perform(f"{server}/get")
        assert code == CURLE_OK
        assert resp == 200
        data = json.loads(body)
        assert data["method"] == "GET"

    def test_get_response_headers(self, server):
        code, resp, _, hdrs = _perform(f"{server}/get")
        assert code == CURLE_OK
        assert "Content-Type" in hdrs

    def test_binary_response(self, server):
        code, resp, body, _ = _perform(f"{server}/binary")
        assert code == CURLE_OK
        assert resp == 200
        assert len(body) == 1024

    def test_user_agent(self, server):
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        _setopt_str(easy, CURLOPT_URL, f"{server}/user-agent".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_str(easy, CURLOPT_USERAGENT, b"libcurl-test/1.0")
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)
        code = lib.curl_easy_perform(easy)
        assert code == CURLE_OK
        data = json.loads(bytes(body))
        assert data["user-agent"] == "libcurl-test/1.0"
        lib.curl_easy_cleanup(easy)


# ---------------------------------------------------------------------------
# Tests: HTTP POST
# ---------------------------------------------------------------------------
class TestPost:
    def test_post_data(self, server):
        payload = "hello=world&test=1"
        code, resp, body, _ = _perform(f"{server}/post", method="POST", data=payload)
        assert code == CURLE_OK
        assert resp == 200
        data = json.loads(body)
        assert data["data"] == payload
        assert data["method"] == "POST"

    def test_post_json(self, server):
        payload = json.dumps({"key": "value"})
        code, resp, body, _ = _perform(
            f"{server}/post", method="POST", data=payload,
            headers=["Content-Type: application/json"],
        )
        assert code == CURLE_OK
        data = json.loads(body)
        assert data["data"] == payload


# ---------------------------------------------------------------------------
# Tests: other HTTP methods
# ---------------------------------------------------------------------------
class TestMethods:
    def test_head(self, server):
        code, resp, body, hdrs = _perform(f"{server}/", nobody=True)
        assert code == CURLE_OK
        assert resp == 200
        assert len(body) == 0
        assert "X-Head-Test" in hdrs

    def test_put(self, server):
        code, resp, body, _ = _perform(f"{server}/put", method="PUT", data="put-data")
        assert code == CURLE_OK
        data = json.loads(body)
        assert data["method"] == "PUT"

    def test_delete(self, server):
        code, resp, body, _ = _perform(f"{server}/delete", method="DELETE")
        assert code == CURLE_OK
        data = json.loads(body)
        assert data["method"] == "DELETE"

    def test_patch(self, server):
        code, resp, body, _ = _perform(f"{server}/patch", method="PATCH", data="patch-data")
        assert code == CURLE_OK
        data = json.loads(body)
        assert data["method"] == "PATCH"


# ---------------------------------------------------------------------------
# Tests: headers
# ---------------------------------------------------------------------------
class TestHeaders:
    def test_custom_headers(self, server):
        code, resp, body, _ = _perform(
            f"{server}/headers",
            headers=["X-Custom-Test: custom-value-123", "X-Another: second"],
        )
        assert code == CURLE_OK
        data = json.loads(body)
        assert data["headers"].get("X-Custom-Test") == "custom-value-123"
        assert data["headers"].get("X-Another") == "second"


# ---------------------------------------------------------------------------
# Tests: redirects
# ---------------------------------------------------------------------------
class TestRedirects:
    def test_follow_redirect(self, server):
        code, resp, body, _ = _perform(f"{server}/redirect", follow=True)
        assert code == CURLE_OK
        assert resp == 200
        data = json.loads(body)
        assert data["method"] == "GET"

    def test_no_follow_redirect(self, server):
        code, resp, _, _ = _perform(f"{server}/redirect")
        assert code == CURLE_OK
        assert resp == 302

    def test_redirect_chain(self, server):
        code, resp, _, _ = _perform(f"{server}/redirect/chain", follow=True)
        assert code == CURLE_OK
        assert resp == 200


# ---------------------------------------------------------------------------
# Tests: status codes
# ---------------------------------------------------------------------------
class TestStatus:
    def test_404(self, server):
        code, resp, _, _ = _perform(f"{server}/status/404")
        assert code == CURLE_OK
        assert resp == 404

    def test_500(self, server):
        code, resp, _, _ = _perform(f"{server}/status/500")
        assert code == CURLE_OK
        assert resp == 500


# ---------------------------------------------------------------------------
# Tests: getinfo
# ---------------------------------------------------------------------------
class TestGetinfo:
    def test_effective_url(self, server):
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        url = f"{server}/get"
        _setopt_str(easy, CURLOPT_URL, url.encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)
        lib.curl_easy_perform(easy)
        eff = _getinfo_str(easy, CURLINFO_EFFECTIVE_URL)
        assert eff == url
        lib.curl_easy_cleanup(easy)

    def test_total_time(self, server):
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        _setopt_str(easy, CURLOPT_URL, f"{server}/get".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)
        lib.curl_easy_perform(easy)
        t = _getinfo_double(easy, CURLINFO_TOTAL_TIME)
        assert t > 0
        lib.curl_easy_cleanup(easy)

    def test_content_type(self, server):
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        _setopt_str(easy, CURLOPT_URL, f"{server}/get".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)
        lib.curl_easy_perform(easy)
        ct = _getinfo_str(easy, CURLINFO_CONTENT_TYPE)
        assert ct is not None and "json" in ct
        lib.curl_easy_cleanup(easy)


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------
class TestErrors:
    def test_bad_url(self):
        code, _, _, _ = _perform("bad://[invalid")
        assert code != CURLE_OK

    def test_connection_refused(self):
        code, _, _, _ = _perform("http://127.0.0.1:1", connect_timeout=2, timeout=3)
        assert code != CURLE_OK

    def test_timeout(self, server):
        code, _, _, _ = _perform(f"{server}/delay", timeout=1, connect_timeout=1)
        assert code != CURLE_OK


# ---------------------------------------------------------------------------
# Tests: HTTPS (against a public endpoint)
# ---------------------------------------------------------------------------
# BinaryBuilder libcurl has no built-in CA bundle. Find the system one.
_CA_BUNDLE = None
for _p in [
    "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",    # RHEL/CentOS
    "/etc/ssl/cert.pem",                   # macOS / Alpine
    "/usr/local/etc/openssl/cert.pem",     # Homebrew OpenSSL
]:
    if os.path.isfile(_p):
        _CA_BUNDLE = _p
        break


class TestHttps:
    def test_https_insecure(self):
        """HTTPS works when peer verification is disabled."""
        code, resp, body, _ = _perform(
            "https://example.com", insecure=True, timeout=30, connect_timeout=10,
        )
        assert code == CURLE_OK
        assert resp == 200
        assert len(body) > 0

    @pytest.mark.skipif(_CA_BUNDLE is None, reason="No system CA bundle found")
    def test_https_with_ca(self):
        """HTTPS works with proper CA verification."""
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        url_b = b"https://example.com"
        ca_b = _CA_BUNDLE.encode()
        _setopt_str(easy, CURLOPT_URL, url_b)
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_str(easy, CURLOPT_CAINFO, ca_b)
        _setopt_long(easy, CURLOPT_TIMEOUT, 30)
        _setopt_long(easy, CURLOPT_CONNECTTIMEOUT, 10)
        code = lib.curl_easy_perform(easy)
        resp = _getinfo_long(easy, CURLINFO_RESPONSE_CODE) if code == CURLE_OK else 0
        lib.curl_easy_cleanup(easy)
        assert code == CURLE_OK, f"HTTPS failed: {lib.curl_easy_strerror(code).decode()}"
        assert resp == 200


# ---------------------------------------------------------------------------
# Tests: multi interface
# ---------------------------------------------------------------------------
class TestMulti:
    def test_multi_lifecycle(self):
        multi = lib.curl_multi_init()
        assert multi is not None and multi != 0
        ret = lib.curl_multi_cleanup(multi)
        assert ret == 0

    def test_multi_add_remove(self, server):
        multi = lib.curl_multi_init()
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        _setopt_str(easy, CURLOPT_URL, f"{server}/get".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)

        ret = lib.curl_multi_add_handle(multi, easy)
        assert ret == 0
        ret = lib.curl_multi_remove_handle(multi, easy)
        assert ret == 0

        lib.curl_easy_cleanup(easy)
        lib.curl_multi_cleanup(multi)

    def test_multi_perform(self, server):
        multi = lib.curl_multi_init()
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)
        _setopt_str(easy, CURLOPT_URL, f"{server}/get".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)

        lib.curl_multi_add_handle(multi, easy)

        still_running = ctypes.c_int(1)
        while still_running.value > 0:
            lib.curl_multi_perform(multi, ctypes.byref(still_running))

        resp = _getinfo_long(easy, CURLINFO_RESPONSE_CODE)
        assert resp == 200
        data = json.loads(bytes(body))
        assert data["method"] == "GET"

        lib.curl_multi_remove_handle(multi, easy)
        lib.curl_easy_cleanup(easy)
        lib.curl_multi_cleanup(multi)

    def test_multi_concurrent(self, server):
        multi = lib.curl_multi_init()
        handles = []
        bodies = []
        callbacks = []

        for endpoint in ["/get", "/user-agent", "/headers"]:
            easy = lib.curl_easy_init()
            body = bytearray()
            cb = _make_write_cb(body)
            _setopt_str(easy, CURLOPT_URL, f"{server}{endpoint}".encode())
            _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
            _setopt_long(easy, CURLOPT_TIMEOUT, 15)
            lib.curl_multi_add_handle(multi, easy)
            handles.append(easy)
            bodies.append(body)
            callbacks.append(cb)

        still_running = ctypes.c_int(1)
        while still_running.value > 0:
            lib.curl_multi_perform(multi, ctypes.byref(still_running))

        for easy, body in zip(handles, bodies):
            resp = _getinfo_long(easy, CURLINFO_RESPONSE_CODE)
            assert resp == 200
            assert len(body) > 0
            lib.curl_multi_remove_handle(multi, easy)
            lib.curl_easy_cleanup(easy)

        lib.curl_multi_cleanup(multi)


# ---------------------------------------------------------------------------
# Tests: reuse handle
# ---------------------------------------------------------------------------
class TestReuse:
    def test_reset_and_reuse(self, server):
        easy = lib.curl_easy_init()
        body = bytearray()
        cb = _make_write_cb(body)

        # First request
        _setopt_str(easy, CURLOPT_URL, f"{server}/get".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb)
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)
        code = lib.curl_easy_perform(easy)
        assert code == CURLE_OK
        assert len(body) > 0

        # Reset and second request
        lib.curl_easy_reset(easy)
        body2 = bytearray()
        cb2 = _make_write_cb(body2)
        _setopt_str(easy, CURLOPT_URL, f"{server}/user-agent".encode())
        _setopt_ptr(easy, CURLOPT_WRITEFUNCTION, cb2)
        _setopt_str(easy, CURLOPT_USERAGENT, b"reuse-test")
        _setopt_long(easy, CURLOPT_TIMEOUT, 15)
        code = lib.curl_easy_perform(easy)
        assert code == CURLE_OK
        data = json.loads(bytes(body2))
        assert data["user-agent"] == "reuse-test"

        lib.curl_easy_cleanup(easy)
