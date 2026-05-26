# ADR-0003: URN Placeholder Naming Alignment with RFC 2606

## Status
Accepted

## Context
The Agent Finder Naming Guide (`spec/urn-naming-guide.md`) mandates that discovery identifiers use a domain-anchored URN namespace format:
`urn:ai:<publisher>:<namespace>:<agent-name>`

To support local development and private sandboxes, developers require placeholder publisher values when they do not own a registered FQDN or cloud namespace. 

Prior versions of the guide informally recommended placeholders like:
* `urn:ai:local.dev:...`
* `urn:ai:local.internal:...`

However:
1. **gTLD Conflict**: The `.dev` suffix is a live, fully resolvable public generic Top-Level Domain (gTLD) owned by Google. Using `.dev` as a private, non-resolvable placeholder violates DNS specifications and can cause name resolution conflicts if validation middleware tries to verify the authority root.
2. **Standards track non-compliance**: Informally invented TLDs (like `.internal` or `.dev` placeholders) violate standard standards-track rules (like IETF RFC 2606 and RFC 6761), which formally reserve specific domains and TLDs for documentation and testing.

## Decision
We aligned all local-development placeholder recommendations in `spec/urn-naming-guide.md` with strictly compliant **RFC 2606** reserved names:

1. **`example.com`** (RFC 2606 §3): The standard reserved domain for documentation and examples.
   * *Compliant URN*: `urn:ai:example.com:<namespace>:<agent-name>`
2. **`.test`** (RFC 2606 §2): A reserved TLD guaranteed to never be registered in the public global DNS root, specifically reserved for testing and local sandbox namespaces.
   * *Compliant URN*: `urn:ai:agent.test:<namespace>:<agent-name>`
3. **`.localhost`** (RFC 2606 §2): A reserved TLD guaranteed to map natively to the loopback address, making it ideal for local development namespaces.
   * *Compliant URN*: `urn:ai:agent.localhost:<namespace>:<agent-name>`

We updated all local manifest examples and scenario descriptions to use `urn:ai:agent.test:...` and `urn:ai:example.com:...` exclusively.

## Consequences
* **DNS Safety**: Guarantees that local test manifests will never conflict with live public DNS hosts or real domain ownership.
* **Compliance**: Fully complies with IETF DNS standards (RFC 2606), paving a smooth path for formal standards-track review under the IETF/AAIF.
* **Uniformity**: Simplifies local conformance validation checking (which can now statically white-list these RFC 2606 roots).
