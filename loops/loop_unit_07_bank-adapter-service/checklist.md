# Verification Checklist: loop_unit_07_bank-adapter-service

- [x] Implement extensible BankAdapter abstract interface for core banking integration
- [x] Implement Awash Finacle adapter mapping standard application model to Awash CBS payload
- [x] Implement bank dynamic field JSONSchema validation for bank-specific intake forms
- [x] Unit tests for schema translation, validation error handling, and tier mapping
- [x] Integration tests executing verified dispatch against running cbs-sandbox
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (external_api)
