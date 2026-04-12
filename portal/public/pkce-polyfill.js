/**
 * PKCE SHA-256 polyfill for non-secure HTTP contexts (local dev only).
 *
 * Problem: oidc-client-ts calls crypto.subtle.digest('SHA-256', ...) for PKCE
 * code challenge generation. On http://*.stoa.local (not a secure context),
 * the browser's crypto.subtle.digest() throws "The operation is insecure".
 * keycloak-js (used by Console) has a built-in JS SHA-256 fallback; this
 * polyfill provides the same capability for the Portal's oidc-client-ts.
 *
 * Guards (defense-in-depth):
 *   1. index.html only loads this script when isSecureContext === false
 *   2. index.html only loads this script on *.local / *.localhost hostnames
 *   3. This script re-checks both conditions before patching
 *
 * On production (HTTPS), none of these conditions are met — the script is
 * never loaded and crypto.subtle is used natively.
 *
 * SHA-256 implementation: FIPS 180-4 compliant, single-block-at-a-time.
 * Not used for security-sensitive operations — only for PKCE code_challenge
 * which is a public value sent in the authorization URL.
 */
(function () {
  'use strict';

  // Defense-in-depth: re-check guards even though index.html already checked
  if (window.isSecureContext) return;
  var h = location.hostname;
  if (!(h.endsWith('.local') || h.endsWith('.localhost') || h === 'localhost')) return;

  // SHA-256 constants (first 32 bits of fractional parts of cube roots of first 64 primes)
  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
    0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
    0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
    0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
    0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
    0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
    0xc67178f2,
  ];

  function sha256(buffer) {
    var bytes = new Uint8Array(buffer);
    // Initial hash values (first 32 bits of fractional parts of square roots of first 8 primes)
    var H = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
      0x5be0cd19,
    ];

    // Pre-processing: padding
    var l = bytes.length;
    var bl = l * 8;
    var msg = new Uint8Array(((l + 9 + 63) & ~63));
    msg.set(bytes);
    msg[l] = 0x80;
    var dv = new DataView(msg.buffer);
    dv.setUint32(msg.length - 4, bl, false);

    // Process each 512-bit block
    for (var off = 0; off < msg.length; off += 64) {
      var w = new Int32Array(64);
      for (var i = 0; i < 16; i++) w[i] = dv.getInt32(off + i * 4, false);
      for (var i = 16; i < 64; i++) {
        var s0 = ((w[i - 15] >>> 7) | (w[i - 15] << 25)) ^ ((w[i - 15] >>> 18) | (w[i - 15] << 14)) ^ (w[i - 15] >>> 3);
        var s1 = ((w[i - 2] >>> 17) | (w[i - 2] << 15)) ^ ((w[i - 2] >>> 19) | (w[i - 2] << 13)) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (var i = 0; i < 64; i++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[i] + w[i]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }

    var out = new ArrayBuffer(32);
    var ov = new DataView(out);
    for (var i = 0; i < 8; i++) ov.setInt32(i * 4, H[i], false);
    return out;
  }

  // Monkey-patch crypto.subtle.digest — preserve native for non-SHA-256 algorithms
  var nativeSubtle = window.crypto && window.crypto.subtle;
  var nativeDigest = nativeSubtle && nativeSubtle.digest.bind(nativeSubtle);
  if (!window.crypto.subtle) window.crypto.subtle = {};
  window.crypto.subtle.digest = function (algo, data) {
    if (typeof algo === 'object') algo = algo.name;
    if (algo.toUpperCase() === 'SHA-256') {
      try {
        return Promise.resolve(sha256(data));
      } catch (e) {
        return Promise.reject(e);
      }
    }
    if (nativeDigest) return nativeDigest(algo, data);
    return Promise.reject(new Error('Unsupported algorithm: ' + algo));
  };

  console.warn('[STOA] crypto.subtle.digest patched for PKCE (non-secure context: ' + location.hostname + ')');
})();
