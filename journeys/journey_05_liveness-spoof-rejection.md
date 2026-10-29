# Journey: Facial Liveness Spoof Detection Rejection
journey_id: J-05
covers: AS-05
priority: critical
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, identity_service, audit_service, db_postgres, cache_redis]

## User Steps (black-box perspective)

1. User successfully completes Fayda OTP verification and advances to the facial liveness capture screen.
2. User presents a printed portrait photo or video replay on an iPad screen toward the camera instead of a live human face.
3. System processes the captured frame stream and immediately returns an error: "Liveness check failed. Please ensure adequate lighting and use a live camera."
4. User attempts spoofed verification two more times (total 3 attempts).
5. System displays "Biometric verification failed. For security purposes, please visit your nearest bank branch with your physical national ID card." App generates a branch reference QR code.

## Required System Components (what must be running)

- `api` — API Gateway and Identity service running local ONNX anti-spoofing model inference.
- `postgres` — PostgreSQL database holding application state.
- `redis` — Redis managing active liveness session state and retry counters.

## Assertion Points (what proves this worked)

- AP-1 API response: `POST /v1/applications/{id}/liveness` returns HTTP 422 with `spoof_detected=true` and anti-spoof score < 0.90.
- AP-2 Database: `applications` status transitions strictly to `LIVENESS_FAILED`.
- AP-3 Storage: Zero raw biometric image frames or video buffers remain in ephemeral filesystem storage after evaluation.
- AP-4 Audit: `audit_logs` records `LIVENESS_VERIFICATION_FAILED` with model version and spoof classification score.

## Failure Modes to Test

- CH-05 Camera stream timeout during frame capture safely resets the session without counting as a fraudulent spoof attempt.
- CH-04 High server load under concurrent ONNX inference enforces strict 2000ms execution timeout preventing worker hanging.
