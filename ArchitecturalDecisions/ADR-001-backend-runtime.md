# ADR-001: Backend Runtime and Web Framework
status: accepted
spec_version: 1

## Context
The platform orchestrates eKYC identity verification, anti-spoofing evaluations, dynamic bank schema validations, and idempotent CBS dispatch. The runtime must handle high concurrent I/O with external gateways while maintaining strict type contracts for financial payloads.

## Options
- **Option 1: Python 3.11+ with FastAPI and Pydantic v2**: Native async event loop, automatic OpenAPI contract generation, seamless integration with ONNX biometric libraries, and high developer velocity.
- **Option 2: Go with Gin/Fiber**: Exceptional raw CPU performance and low memory footprint; however, dynamic JSONSchema evaluation and machine learning model bindings require complex CGO or external RPC bridges.
- **Option 3: Node.js / TypeScript with NestJS**: Shared language typing with web frontends; however, biometric anti-spoofing and face comparison libraries lack robust native Node.js ecosystems and require Python sidecars.

## Decision
Adopt **Python 3.11+ with FastAPI and Pydantic v2** as the core backend service framework.

## Rationale
Cites `research/prior_art.md` §Reusable OSS Candidates ("FastAPI + Pydantic v2: High-throughput asynchronous REST API, OpenAPI contract generation, strict typing and serialization for banking payloads") and `research/brainstorm.md` §User-Facing Requirements (Requirement 4 & 7: eKYC and dynamic bank schema validation).

## Consequences
- Single unified runtime simplifies operational footprint in Phase 1 pilot.
- Async endpoints prevent thread exhaustion during high-latency bank CBS calls.
- Strict Pydantic schemas eliminate invalid data ingress at the API boundary.
