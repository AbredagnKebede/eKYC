# ADR-009: Deployment Sovereignty and Containerization
status: accepted
spec_version: 1

## Context
National Bank of Ethiopia directives mandate in-country data localization for financial systems processing citizen identity and banking data. The infrastructure must be completely sovereign, portable across local Ethiopian hosting providers (e.g. Ethio Telecom Cloud, Raxio, Wingu), and run without dependencies on foreign hyper-scaler specific services.

## Options
- **Option 1: Standardized Containerization (Docker & OCI Images) with Docker Compose / Kubernetes Manifests**: 100% portable, reproducible across local bare-metal or sovereign cloud VMs, zero cloud-provider lock-in.
- **Option 2: AWS / GCP Proprietary Serverless (Lambda, Cloud Run, DynamoDB)**: Rapid setup; however, directly violates data localization requirements as global cloud providers lack local regions in Ethiopia.
- **Option 3: Bare-Metal Manual Installation (systemd / apt scripts)**: High maintenance overhead, prone to configuration drift, and difficult to verify deterministically in CI/CD pipeline loops.

## Decision
Deploy all backend services, database instances, and caching infrastructure as **OCI-compliant containers (Docker)** orchestrated via **Docker Compose** for development/pilot, ready for Kubernetes (k8s) in production sovereign data centers.

## Rationale
Cites `research/brainstorm.md` §Confirmed Intent (Bullet 14: "hosted in-country in compliance with National Bank of Ethiopia (NBE) data localization directives") and `dependency_list.md` (DEP-004: "In-country cloud hosting infrastructure availability").

## Consequences
- Guarantees 100% compliance with Ethiopian financial data localization regulations.
- Enables reproducible automated verification in CI pipelines and local developer environments.
- Allows seamless migration between local data center operators without architectural rewrites.
