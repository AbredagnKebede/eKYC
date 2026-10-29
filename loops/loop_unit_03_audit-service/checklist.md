# Verification Checklist: loop_unit_03_audit-service

- [ ] Implement cryptographic SHA-256 hash chaining over sequential audit log records
- [ ] Implement HMAC-SHA256 seal generation using environment secret key
- [ ] Implement audit ledger verification function to detect tampering or broken chains
- [ ] Unit tests for hash chain hashing logic, tamper detection, and HMAC verification
- [ ] Integration tests verifying atomic persistence of audit records in PostgreSQL
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (db)
