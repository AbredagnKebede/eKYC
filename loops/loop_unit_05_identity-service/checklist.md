# Verification Checklist: loop_unit_05_identity-service

- [x] Implement AES-256-GCM encryption/decryption for demographic PII snapshots
- [x] Implement salted HMAC-SHA256 hashing for Fayda FIN/FAN numbers (zero plaintext retention)
- [x] Implement ONNX anti-spoofing and face comparison inference engine (liveness score threshold 0.90, cosine 0.82)
- [x] Unit tests for encryption round-trip, FIN hashing, and model threshold guards
- [x] Integration tests verifying real database encryption and live Fayda sandbox verification handshake
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (db, external_api)
