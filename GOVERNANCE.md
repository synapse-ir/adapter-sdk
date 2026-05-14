# SYNAPSE Project Governance

This document describes how the SYNAPSE project is governed, how decisions are made, and how contributors can gain additional responsibilities over time. It will evolve as the community grows.

---

## Project mission

SYNAPSE provides an open canonical intermediate representation (IR) and adapter framework for heterogeneous AI model pipelines. Its mission is to solve the schema incompatibility problem between specialist AI models, reducing the N×M connector problem to a 2N adapter problem, and to enable routing intelligence and calibration that improves over time from real production signals.

The canonical IR specification is published under CC BY 4.0. The adapter SDK, registry server, and all reference adapters are published under the MIT License. Both licenses are OSI-approved.

---

## Current governance structure

SYNAPSE is currently in its initial phase of development. The project was founded and is currently maintained by a single founding maintainer. This governance document describes the current structure honestly and defines how governance evolves as the contributor community grows.

### Founding Maintainer

**Chris Widmer** is the current Founding Maintainer and holds overall responsibility for the project's technical direction, release process, specification changes, and community standards.

Responsibilities of the Founding Maintainer:

- Set and communicate the project's technical direction and roadmap
- Review and merge pull requests across all repositories
- Approve or decline proposals for changes to the canonical IR specification
- Manage releases and version numbering
- Enforce the Code of Conduct
- Represent the project in external governance discussions, including with the LF AI & Data Foundation
- Onboard new maintainers as the contributor community grows

The Founding Maintainer role is held until a Technical Steering Committee (TSC) is established per the process defined below.

---

## Contributor roles

### Contributor

Anyone who submits a pull request, opens an issue, writes documentation, or participates constructively in project discussions is a Contributor. There are no formal requirements to be a Contributor. All Contributors must follow the project's Code of Conduct.

### Adapter Author

A Contributor who has published at least one validated adapter to the synapse-ir/adapters repository is recognized as an Adapter Author. Adapter Authors are listed in the adapters repository's CONTRIBUTORS.md file and are credited as Founding Contributors if their adapter is among the first ten published.

### Maintainer

A Maintainer has sustained, high-quality contributions across code, documentation, or ecosystem development and has demonstrated judgment consistent with the project's technical direction. Maintainers have write access to one or more project repositories and participate in code review and release decisions.

**How to become a Maintainer:**

Any Contributor may be nominated for Maintainer status by the Founding Maintainer or by an existing Maintainer, after demonstrating:

- At least three merged pull requests of meaningful scope across any project repository
- Consistent engagement with issues and pull requests from other contributors
- Familiarity with the canonical IR specification and adapter contract
- Alignment with the project's technical direction and Code of Conduct

Nominations are announced publicly in the project's GitHub Discussions. The Founding Maintainer (or, once established, the TSC) approves or declines nominations within 14 days. Approved Maintainers are added to MAINTAINERS.md.

A Maintainer may voluntarily step down by notifying the Founding Maintainer. Maintainers who have been inactive for six months or more may be moved to Emeritus status after notification.

---

## Decision making

### Day-to-day decisions

Routine decisions — bug fixes, documentation improvements, minor feature additions, patch releases — are made by any Maintainer with write access through the normal pull request review process. A pull request requires at least one Maintainer approval before merging. The author of a pull request may not merge their own pull request unless no other Maintainer is available within seven days and the change is non-breaking.

### Significant decisions

Significant decisions include:

- Changes to the canonical IR specification (any version bump)
- New task_type or domain registrations
- Changes to the adapter validation rules
- Major or minor SDK version releases
- Addition or removal of Maintainers
- Changes to this governance document

Significant decisions are made by the Founding Maintainer (or, once the TSC is established, by TSC consensus) after a minimum seven-day public comment period announced in GitHub Discussions. Community members are encouraged to comment during this period. The decision and its rationale are documented publicly.

### Specification changes

Changes to the canonical IR specification (github.com/synapse-ir/spec) follow a structured process:

1. A proposal is opened as a GitHub issue in the spec repository with the label `proposal`
2. A minimum 14-day public comment period applies to all proposals
3. MAJOR version changes (breaking) require broader community input and a longer comment period of at least 30 days
4. The Founding Maintainer (or TSC) documents the final decision and rationale in the issue before closing

---

## Technical Steering Committee (TSC)

A Technical Steering Committee will be established when the project reaches a community scale that warrants distributed governance. The TSC formation criteria are:

- At least three organizations actively contributing to the project
- At least three individuals willing to serve as TSC members from at least two different organizations
- The project has been accepted as an LF AI & Data Sandbox or Incubation project

When these criteria are met, the Founding Maintainer will initiate TSC formation by:

1. Announcing the intent to form a TSC in GitHub Discussions with a 30-day comment period
2. Soliciting nominations for TSC members from the Maintainer pool
3. Establishing the initial TSC by consensus among existing Maintainers
4. Updating this governance document to reflect TSC procedures

Once established, the TSC will hold decision-making authority for significant decisions. TSC decisions are made by consensus where possible and by simple majority vote when consensus cannot be reached. All TSC votes and decisions are documented publicly.

---

## Code of Conduct

All participants in the SYNAPSE project — Contributors, Adapter Authors, Maintainers, and TSC members — are expected to follow the project's Code of Conduct, published at CODE_OF_CONDUCT.md in the adapter-sdk repository.

The project adopts the Contributor Covenant v2.1 as its Code of Conduct. Reports of Code of Conduct violations may be sent to the Founding Maintainer. When a TSC is established, a dedicated Code of Conduct committee will be formed.

---

## Security

Security vulnerabilities should be reported privately, not through public GitHub issues. See SECURITY.md for the full vulnerability reporting process. Security issues are handled with priority and reporters are credited in release notes unless they request otherwise.

### Two-factor authentication

All Maintainers and anyone with write access to any repository in the `synapse-ir` GitHub organisation **must** enable two-factor authentication on their GitHub account. The organisation enforces this at the settings level. Only cryptographic methods are accepted: a hardware security key (FIDO2/WebAuthn) or a TOTP authenticator app. SMS-only 2FA does not meet this requirement. Accounts that do not satisfy the requirement will be removed from the organisation until compliance is confirmed.

---

## Relationship with LF AI & Data Foundation

SYNAPSE is applying for Sandbox hosting under the LF AI & Data Foundation. If accepted:

- The SYNAPSE trademark will be held by LF AI & Data on the project's behalf
- The project will operate under LF AI & Data's neutral governance framework
- A Technical Charter will be established in coordination with LF AI & Data staff
- This governance document will be updated to reflect the Technical Charter requirements

The open source licenses (MIT and CC BY 4.0) are not affected by foundation hosting. The specification and code remain available to all under their published licenses regardless of governance structure.

---

## Amendment process

This governance document may be amended by the Founding Maintainer (or, once established, by TSC consensus) after a minimum 14-day public comment period. All amendments are announced in GitHub Discussions. The history of this document is maintained in version control.

---

*Last updated: May 2026*
*Founding Maintainer: Chris Widmer*
*Project: SYNAPSE — Schema Yielding Normalized Agent Pipeline Signal Engine*
*Repositories: github.com/synapse-ir*
