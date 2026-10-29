# Verification Checklist: loop_unit_05_identity-service

- [ ] Implement AES-256-GCM encryption/decryption for demographic PII snapshots
- [ ] Implement salted HMAC-SHA256 hashing for Fayda FIN/FAN numbers (zero plaintext retention)
- [ ] Implement ONNX anti-spoofing and face comparison inference engine (liveness score threshold 0.90, cosine 0.82)
- [ ] Unit tests for encryption round-trip, FIN hashing, and model threshold guards
- [ ] Integration tests verifying real database encryption and live Fayda sandbox verification handshake
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (db, external_api)
