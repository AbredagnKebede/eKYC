# Verification Checklist: loop_unit_07_bank-adapter-service

- [ ] Implement extensible BankAdapter abstract interface for core banking integration
- [ ] Implement Awash Finacle adapter mapping standard application model to Awash CBS payload
- [ ] Implement bank dynamic field JSONSchema validation for bank-specific intake forms
- [ ] Unit tests for schema translation, validation error handling, and tier mapping
- [ ] Integration tests executing verified dispatch against running cbs-sandbox
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (external_api)
