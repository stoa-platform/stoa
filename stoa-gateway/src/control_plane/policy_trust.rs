//! Pinned trust set for signed tool-policy artifacts.
//!
//! Artifacts are verified only against the public keys in the JWKS file at
//! `STOA_POLICY_TRUST_JWKS_FILE`; nothing is fetched from the network. The
//! whole file is refused unless every entry is an Ed25519 `OKP` key with
//! `alg=EdDSA` and a unique `kid`, and at most two keys are listed (current
//! plus backup). A missing or refused set leaves the gateway fail-closed.
//! Write access to this file must be restricted exactly as for the Control
//! Plane private signing key: whoever can edit it chooses the trusted signer.

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use jsonwebtoken::jwk::{AlgorithmParameters, EllipticCurve, JwkSet, KeyAlgorithm};
use jsonwebtoken::DecodingKey;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, RwLock};
use thiserror::Error;
use tracing::{info, warn};

/// Maximum number of keys in the pinned set (current + backup).
pub const MAX_TRUSTED_KEYS: usize = 2;

/// Why a JWKS file was refused. Carries neither the file path nor key material.
#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum TrustSetError {
    #[error("trust set file unreadable")]
    Unreadable,
    #[error("trust set is not a valid JWKS document")]
    Malformed,
    #[error("trust set lists {0} keys, expected 1 to {MAX_TRUSTED_KEYS}")]
    KeyCount(usize),
    #[error("trust set key is not an Ed25519 OKP key with alg=EdDSA and a unique kid")]
    InvalidKey,
}

/// Validated, immutable set of signer public keys indexed by `kid`.
#[derive(Clone)]
pub struct PolicyTrustSet {
    keys: HashMap<String, DecodingKey>,
}

impl PolicyTrustSet {
    /// Parse a JWKS document. Any invalid entry refuses the whole set.
    pub fn parse(json: &[u8]) -> Result<Self, TrustSetError> {
        let set: JwkSet = serde_json::from_slice(json).map_err(|_| TrustSetError::Malformed)?;
        if set.keys.is_empty() || set.keys.len() > MAX_TRUSTED_KEYS {
            return Err(TrustSetError::KeyCount(set.keys.len()));
        }
        let mut keys = HashMap::new();
        for jwk in &set.keys {
            let x = match &jwk.algorithm {
                AlgorithmParameters::OctetKeyPair(p) if p.curve == EllipticCurve::Ed25519 => &p.x,
                _ => return Err(TrustSetError::InvalidKey),
            };
            // jsonwebtoken slices 32 bytes at verify time: check the length once here.
            let x_len = URL_SAFE_NO_PAD.decode(x).map_or(0, |raw| raw.len());
            if x_len != 32 || jwk.common.key_algorithm != Some(KeyAlgorithm::EdDSA) {
                return Err(TrustSetError::InvalidKey);
            }
            let kid = jwk.common.key_id.clone().filter(|kid| !kid.is_empty());
            let key = DecodingKey::from_jwk(jwk).map_err(|_| TrustSetError::InvalidKey)?;
            if keys
                .insert(kid.ok_or(TrustSetError::InvalidKey)?, key)
                .is_some()
            {
                return Err(TrustSetError::InvalidKey);
            }
        }
        Ok(Self { keys })
    }

    /// Public key for `kid`, if it is part of the pinned set.
    pub fn key(&self, kid: &str) -> Option<&DecodingKey> {
        self.keys.get(kid)
    }
}

/// Reloadable holder for the pinned trust set. `None` means "trust set not
/// loaded". A refused reload replaces any previously loaded set, so a key
/// removed from the file stops verifying immediately.
pub struct PolicyTrustStore {
    path: PathBuf,
    current: RwLock<Option<PolicyTrustSet>>,
}

impl PolicyTrustStore {
    /// Load the file once. A failure leaves the store unloaded (fail closed).
    pub fn open(path: impl Into<PathBuf>) -> Arc<Self> {
        let store = Arc::new(Self {
            path: path.into(),
            current: RwLock::default(),
        });
        let _ = store.reload();
        store
    }

    /// Re-read the file and swap the set atomically. Returns the key count.
    pub fn reload(&self) -> Result<usize, TrustSetError> {
        let result = std::fs::read(&self.path)
            .map_err(|_| TrustSetError::Unreadable)
            .and_then(|bytes| PolicyTrustSet::parse(&bytes));
        match &result {
            Ok(set) => info!(keys = set.keys.len(), "Policy trust set loaded"),
            Err(reason) => warn!(reason = %reason, "Policy trust set not loaded"),
        }
        if let Ok(mut current) = self.current.write() {
            *current = result.as_ref().ok().cloned();
        }
        result.map(|set| set.keys.len())
    }

    /// Snapshot of the loaded set; `None` while the trust set is not loaded.
    pub fn current(&self) -> Option<PolicyTrustSet> {
        self.current.read().ok().and_then(|set| set.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::TrustSetError::{InvalidKey, KeyCount, Malformed};
    use super::*;
    use jsonwebtoken::{Algorithm, EncodingKey, Header, Validation};
    use serde_json::{json, Value};

    /// RFC 8032 §7.1 test vectors (PKCS#8 DER and public key `x`, base64url).
    /// Published and deterministic: they are not real signing keys. Indexes
    /// beyond the vectors reuse key material under a new `kid`.
    const DER: [&str; 2] = [
        "MC4CAQAwBQYDK2VwBCIEIJ1hsZ3v_VpguoRK9JLsLMREScVpezJpGXA7rAMcrn9g",
        "MC4CAQAwBQYDK2VwBCIEIEzNCJso_5banbbDRuwRTg9bijGfNaumJNqM9u1PuKb7",
    ];
    const X: [&str; 2] = [
        "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
        "PUAXw-hDiVqStwqnTRt-vJyYLM8uxJaMwM1V8Sr0Zgw",
    ];

    fn okp(i: usize) -> Value {
        let x = X[i % 2];
        json!({"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "kid": format!("k{i}"), "x": x})
    }

    fn jwks(keys: &[Value]) -> Vec<u8> {
        json!({ "keys": keys }).to_string().into_bytes()
    }

    fn refused(keys: &[Value]) -> TrustSetError {
        PolicyTrustSet::parse(&jwks(keys)).err().unwrap()
    }

    fn sign(i: usize) -> String {
        let key = EncodingKey::from_ed_der(&URL_SAFE_NO_PAD.decode(DER[i % 2]).unwrap());
        let mut header = Header::new(Algorithm::EdDSA);
        header.kid = Some(format!("k{i}"));
        jsonwebtoken::encode(&header, &json!({"v": i}), &key).unwrap()
    }

    fn verify(set: &PolicyTrustSet, jws: &str) -> Result<(), &'static str> {
        let kid = jsonwebtoken::decode_header(jws).ok().and_then(|h| h.kid);
        let key = set.key(&kid.ok_or("no kid")?).ok_or("unknown kid")?;
        let mut validation = Validation::new(Algorithm::EdDSA);
        validation.validate_exp = false;
        validation.validate_aud = false;
        validation.required_spec_claims.clear();
        jsonwebtoken::decode::<Value>(jws, key, &validation)
            .map(|_| ())
            .map_err(|_| "bad signature")
    }

    #[test]
    fn two_keys_are_accepted_and_a_third_refuses_the_set() {
        let set = PolicyTrustSet::parse(&jwks(&[okp(0), okp(1)])).unwrap();
        assert_eq!(verify(&set, &sign(0)), Ok(()));
        assert_eq!(verify(&set, &sign(1)), Ok(()));
        assert_eq!(verify(&set, &sign(2)), Err("unknown kid"));
        assert_eq!(refused(&[okp(0), okp(1), okp(2)]), KeyCount(3));
    }

    #[test]
    fn mixed_or_invalid_sets_are_refused_as_a_whole() {
        let ec = json!({"kty":"EC","crv":"P-256","alg":"ES256","kid":"ec","x":"AA","y":"AA"});
        assert_eq!(refused(&[okp(0), ec]), InvalidKey);
        // An empty value removes the field (serialized as null).
        for (field, value) in [("alg", "ES256"), ("alg", ""), ("kid", ""), ("kid", "k0")] {
            let mut key = okp(1);
            key[field] = json!(Some(value).filter(|v| !v.is_empty()));
            assert_eq!(refused(&[okp(0), key]), InvalidKey);
        }
        assert_eq!(refused(&[]), KeyCount(0));
        assert_eq!(PolicyTrustSet::parse(b"not json").err().unwrap(), Malformed);
    }

    #[test]
    fn removing_a_key_refuses_its_artifacts() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("trust.json");
        std::fs::write(&path, jwks(&[okp(0), okp(1)])).unwrap();
        let store = PolicyTrustStore::open(&path);
        assert_eq!(verify(&store.current().unwrap(), &sign(0)), Ok(()));

        std::fs::write(&path, jwks(&[okp(1)])).unwrap();
        assert_eq!(store.reload(), Ok(1));
        let set = store.current().unwrap();
        assert_eq!(verify(&set, &sign(0)), Err("unknown kid"));
        assert_eq!(verify(&set, &sign(1)), Ok(()));

        // A refused rewrite must not leave the previous set in force.
        std::fs::write(&path, jwks(&[okp(0), okp(1), okp(2)])).unwrap();
        assert_eq!(store.reload(), Err(KeyCount(3)));
        assert!(store.current().is_none());
    }
}
