/*
 * Non-variadic wrappers around curl_easy_setopt / curl_easy_getinfo.
 *
 * On Apple ARM64, variadic and non-variadic functions use different calling
 * conventions (variadic args go on the stack, non-variadic in registers).
 * Python's ctypes cannot reliably call C variadic functions on this platform.
 * These thin wrappers present a non-variadic ABI that ctypes can call safely.
 */
#include <curl/curl.h>

CURLcode curl_setopt_long(CURL *curl, CURLoption option, long value) {
    return curl_easy_setopt(curl, option, value);
}

CURLcode curl_setopt_str(CURL *curl, CURLoption option, const char *value) {
    return curl_easy_setopt(curl, option, value);
}

CURLcode curl_setopt_ptr(CURL *curl, CURLoption option, void *value) {
    return curl_easy_setopt(curl, option, value);
}

CURLcode curl_getinfo_ptr(CURL *curl, CURLINFO info, void *out) {
    return curl_easy_getinfo(curl, info, out);
}
