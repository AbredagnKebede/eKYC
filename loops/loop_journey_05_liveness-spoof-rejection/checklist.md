# Journey Checklist: loop_journey_05_liveness-spoof-rejection

- [ ] AP-1 ONNX inference engine detects static/replayed face frame and returns spoof score < 0.90
- [ ] AP-2 Rejection response returned with HTTP 422 and actionable remediation prompt
- [ ] AP-3 After 3 consecutive spoof rejections, application state transitions to LIVENESS_FAILED in database
- [ ] AP-4 Biometric image frame buffers are purged from memory with zero persistent file retention
- [ ] 100% of assertion points verified by black-box tests in tests/journey/j05
- [ ] Zero mocks at critical boundaries (db)
- [ ] Real processes and sandbox services running
