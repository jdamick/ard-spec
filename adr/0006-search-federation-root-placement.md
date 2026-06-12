# ADR-0006: Search API Federation Parameter Placement

## Status
Accepted (Implemented in v0.5.0)

## Context
In the v0.4 design profile of the Agentic Resource Discovery specification, the search `federation` control parameter (`auto`, `referrals`, `none`) was placed inside the nested `query` object of the `POST /search` request payload.

As the Working Group expanded the standard in v0.5.0 to formally introduce the dynamic `/explore` endpoint—adopting a unified Shared Query Model—we re-evaluated the architectural placement and lifecycle scope of the federation parameter.

The core architectural considerations were:
1. **Scope Definition**: The `federation` parameter does not control *what* to search (the semantic intent or metadata filtering constraints of the request), but rather *how and where* the registry executes and routes the request across the wider network topology.
2. **Explore Boundary Alignment**: Per our discussions, the dynamic `/explore` introspection API does NOT support federation to protect server capability maps from comparative math skew. Keeping `federation` isolated to the `POST /search` root interface prevents this operation from leaking into the shared `QueryModel` used by `/explore`.

## Decision
We moved the `federation` parameter from the nested `query` block to the **root level** of the `POST /search` request payload schema.

It now sits as a root-level sibling to the `query` object, `pageSize`, and `pageToken` parameters. 

## Consequences
* **Clean Query Object Separation**: The shared `QueryModel` referenced by both `/search` and `/explore` remains 100% identical and focused strictly on matching criteria.
* **Explicit Federation Visibility**: Network routing intent is explicitly visible to HTTP gateways and middleware at the top level of the payload without deep JSON traversal.
