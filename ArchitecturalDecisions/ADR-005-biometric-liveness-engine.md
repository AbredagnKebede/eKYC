# ADR-005: Biometric Liveness and Face Comparison Engine
status: accepted
spec_version: 1

## Context
Verifying the user requires evaluating facial anti-spoofing (detecting printed photos, video replay, and silicone masks) and matching the selfie against the official credential photo returned by Fayda eKYC. External cloud computer vision APIs (e.g. AWS Rekognition) violate data sovereignty directives and incur recurrent per-check costs.

## Options
- **Option 1: Embedded ONNX Runtime with Silent-Face-Anti-Spoofing and FaceNet**: Zero external SaaS dependency, runs locally within the backend container, sub-second CPU inference, and model weights optimized via quantization.
- **Option 2: Commercial SaaS (Smile Identity / SumSub / Onfido)**: Fully managed; however, routes biometric data outside Ethiopia in violation of data sovereignty assumptions and introduces substantial per-verification dollar fees.
- **Option 3: Pure Client-Side Only Evaluation**: Vulnerable to client-side binary reverse engineering, hooked camera feeds, and manipulated HTTP response payloads.

## Decision
Adopt **server-side ONNX Runtime** running **Silent-Face-Anti-Spoofing** (for passive 2D/3D replay detection) coupled with **FaceNet (Inception-ResNet-v1)** embeddings for cosine-similarity face comparison, with lightweight client-side frame pre-validation.

## Rationale
Cites `research/prior_art.md` §Reusable OSS Candidates ("Silent-Face-Anti-Spoofing / ONNX Runtime: Deepfake and photo/screen replay attack detection running on lightweight ONNX weights without external commercial vendor dependencies") and `research/brainstorm.md` §Confirmed Intent (Bullet 6: "Biometric Liveness & Facial Comparison").

## Consequences
- 100% data sovereignty: all biometric computation occurs within the local deployment perimeter.
- Zero marginal vendor licensing cost per verification.
- Quantized models execute on standard modern CPU infrastructure without requiring dedicated GPU instances.
