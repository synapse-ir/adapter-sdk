# Security Policy

## Reporting a vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

If you believe you have found a security vulnerability in any SYNAPSE repository, please report it privately using one of the following methods:

**Preferred: GitHub private vulnerability reporting**

Use GitHub's built-in private vulnerability reporting feature on any SYNAPSE repository:

1. Go to the affected repository on GitHub (for example, github.com/synapse-ir/adapter-sdk)
2. Click the **Security** tab
3. Click **Report a vulnerability**
4. Complete the form and submit

This creates a private security advisory visible only to the maintainers. GitHub notifies the maintainer immediately.

**Alternative: Email**

Send a description of the vulnerability to:

```
security@synapse-ir.io
```

If the email address is not yet active, contact the Founding Maintainer directly through GitHub: github.com/synapse-ir

**What to include in your report:**

- Which repository and component is affected
- A description of the vulnerability and what an attacker could do with it
- Steps to reproduce the issue
- The version of the SDK, registry, or specification you were using
- Any potential impact you have identified

You do not need a proof-of-concept exploit to report. A clear description of the issue is sufficient.

---

## Response timeline

We take security reports seriously and will respond as promptly as possible given that this is currently a solo-maintained project.

| Milestone | Target timeline |
|---|---|
| Acknowledgement of report | Within 72 hours |
| Initial triage and severity assessment | Within 7 days |
| Fix or mitigation plan communicated to reporter | Within 30 days for Critical and High severity |
| Public disclosure | Coordinated with reporter after fix is available |

If you do not receive an acknowledgement within 72 hours, please follow up through GitHub directly.

---

## Severity levels

We assess severity using the Common Vulnerability Scoring System (CVSS) framework as a guide, combined with SYNAPSE-specific context.

| Severity | Description |
|---|---|
| **Critical** | Allows remote code execution, arbitrary data access, or complete compromise of the registry server or SDK host process. Payload injection resulting in code execution. |
| **High** | Allows authentication bypass, unauthorized registry access, or significant data exposure. IR validation bypass that allows malformed payloads to reach downstream models. |
| **Medium** | Allows denial of service, rate limit bypass, or provenance chain tampering that does not result in code execution. |
| **Low** | Minor information disclosure, log injection, or edge-case validation gaps with limited practical impact. |

---

## SYNAPSE-specific security model

Understanding SYNAPSE's security model helps reporters identify what constitutes a vulnerability versus intended behavior.

**Adapter functions are intentionally pure**

Adapters are required by the specification to be pure functions with no network calls and no persistent state. The AdapterValidator checks for imports of network libraries (requests, httpx, urllib, socket, aiohttp) at validation time. A vulnerability would be: a way to bypass this check and execute network calls or system commands from inside an adapter function.

**The canonical IR carries untrusted payload content**

The `payload.content` field in the canonical IR contains user-supplied text. This content is treated as data throughout the SYNAPSE stack — it is never evaluated, executed, or used to construct dynamic code. Null bytes are rejected at IR construction time. A vulnerability would be: a way to cause SYNAPSE's own code to interpret payload content as instructions or executable code.

**The registry API accepts untrusted manifests**

The registry receives capability manifests from model developers. Manifest fields are stored and served verbatim — they are never executed or evaluated. A vulnerability would be: a way to cause the registry to execute or interpret content from a submitted manifest field.

**Authentication tokens protect write operations**

Registry write operations (model registration, manifest updates, calibration signal submission) require a valid bearer token. Read operations are unauthenticated on the open-source registry. A vulnerability would be: a way to perform write operations without a valid token, or to access another organization's models or tokens.

**Adapter supply chain**

Adapters are Python packages published to PyPI. The registry verifies package existence on PyPI at registration time. A vulnerability would be: a way to register an adapter package that executes arbitrary code at import time in a way that bypasses the NO_NETWORK_CALLS validator.

---

## Out of scope

The following are not considered security vulnerabilities for the purposes of this policy:

- Vulnerabilities in third-party dependencies (report these to the dependency maintainer directly)
- Social engineering attacks
- Physical access attacks
- Denial of service through legitimate API usage within documented rate limits
- Issues that require the attacker to already have administrator access to the host system
- Bugs in adapters written by third parties and published independently to PyPI

---

## Coordinated disclosure

We follow responsible disclosure practices. We ask that you:

- Give us a reasonable opportunity to investigate and address the issue before public disclosure
- Avoid accessing, modifying, or deleting data that does not belong to you during research
- Avoid disrupting the hosted registry service for other users

In return, we commit to:

- Acknowledging your report promptly
- Keeping you informed of progress toward a fix
- Crediting you in the security advisory and release notes unless you request otherwise
- Not pursuing legal action against good-faith security researchers who follow this policy

---

## Security advisories

Published security advisories are available in the Security tab of each repository:

- github.com/synapse-ir/adapter-sdk/security/advisories
- github.com/synapse-ir/registry/security/advisories

---

## Supported versions

Security fixes are applied to the most recent published version of the SDK and registry. Older versions do not receive backported security patches unless the vulnerability is critical and the fix is straightforward to backport.

| Component | Supported version |
|---|---|
| synapse-adapter-sdk (PyPI) | Latest published version |
| @synapse-ir/adapter-sdk (npm) | Latest published version |
| synapse-registry | Latest published Docker image |
| Canonical IR Specification | Current published version at github.com/synapse-ir/spec |

---

*Last updated: May 2026*
*Maintained by: Chris Widmer (github.com/synapse-ir)*
