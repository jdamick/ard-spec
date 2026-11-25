# ADR-0013: Search and List Results Are AI Catalog Entries

## Status
Proposed

## Context
[ADR-0010](0010-ard-and-ai-catalog-loose-coupling.md) says an ARD entry is the AI Catalog entry core plus namespaced
terms, but ARD's results don't follow it. §5.3.2 requires only `identifier` in a Search result and leaves every other
term to the registry, so a result is an ARD-specific fragment, not an AI Catalog entry. A client can't store or
republish one as a Catalog Entry, and an AI Catalog consumer can't read one, without fetching the full entry again.
List (§5.3.4) has the same shape.

AI Catalog's [Catalog Entry](https://github.com/Agent-Card/ai-catalog/blob/19208af2f8adbc0a6457e3ff36ce691a304fbd97/specification/ai-catalog.md#catalog-entry)
(v0.9, the 1.0 release candidate) requires `identifier`, `type` and exactly one of `url` or `data`. Since AI Catalog's
[ADR-0028](https://github.com/Agent-Card/ai-catalog/blob/19208af2f8adbc0a6457e3ff36ce691a304fbd97/adr/0028-open-catalog-and-entry-objects.md)
(open catalog and entry objects, agreed 2026-11-05), its CDDL map is open (`* text => any`), so a Catalog Entry may carry members AI Catalog doesn't
define, such as ARD's `score`, `source` and discovery terms.

This is gap G2 in [issue 117](https://github.com/ards-project/ard-spec/issues/117). Issue 117 lists three shapes:

- (1) `{entry, score, source}`, the entry nested;
- (2) the entry's members at the top level, with `score` and `source` beside them;
- (3) a search response that is itself an AI Catalog document.

## Decision
A Search result is an AI Catalog Catalog Entry with ARD's `score` and `source` as top-level members beside the entry's
own, shape (2). A List item is a Catalog Entry.

1. **Required members.** A result carries what a Catalog Entry requires: `identifier`, `type` and exactly one of `url`
   or `data`. A registry MAY omit every other term, as before.
2. **Result members.** `score` and `source` describe the response, not the resource. A client that stores or
   republishes a result as an AI Catalog entry MUST remove them, or a downstream catalog shows one registry's
   relevance for one query as an attribute of the resource. A List item SHOULD NOT carry them.
3. **CDDL.** `search-result-item` is `{ score, source, ard-result-terms, ~CatalogEntry }`, and `list-item` is
   `{ ard-result-terms, ~CatalogEntry }`. `ard-result-terms` types the ARD terms AI Catalog doesn't define:
   `@context`, `@id`, `capabilities`, `representativeQueries`, `metadata` and `trustManifest`.
4. **Vendored grammar.** `CatalogEntry` comes from `spec/schemas/ai-catalog.cddl`, AI Catalog's CDDL copied
   unchanged at commit 19208af with an attribution header (CC BY 4.0). RFC 8610 has no import, so payloads are
   validated against both files together.
5. **OpenAPI and tooling.**
   - `SearchResultItem` and the List items require `identifier` and `type`, and require exactly one of `url` or
     `data`.
   - The conformance tool's registry mode checks the same.

### Alternatives considered
- **(1) Nested entry.** The entry stays an untouched Catalog Entry, and `score` and `source` can't collide with a
  member AI Catalog defines later. It changes every v0.91 client's path from `results[].identifier` to
  `results[].entry.identifier`. Rejected in favour of the flat shape, which keeps that path.
- **(3) AI Catalog document.** Results become `entries` of a catalog, with scores, referrals and the page token moved
  under `extensions`. Every response is a valid AI Catalog document, but relevance moves into a side map keyed by
  identifier, and Explore and List don't fit the shape.
- **Keep identifier-only results.** No change for registries, but results remain unusable as Catalog Entries, which
  is what G2 asks for.

## Consequences
- **Breaking for registries.** A registry that returns identifier-only results, or results without `type`, no longer
  conforms. Clients reading only `identifier`, `score` and `source` are unaffected.
- **Collision risk.** AI Catalog treats unrecognized members as having "No Stability Guarantee", so a future AI
  Catalog member named `score` or `source` would collide with ARD's. Shape (1) avoids this. ARD would then move its
  members under a namespace (G3) or a nested object.
- **Grammar maintenance.** `ai-catalog.cddl` changes only when ARD moves its pinned AI Catalog commit, in the same
  way as the bundled `ai-catalog.schema.json`.
- **Validation tooling.** No unmodified CDDL tool validates the unwrap today.
  - The reference `cddl` gem 0.12.14 crashes on a group choice pulled in by `~`, and CatalogEntry's
    `(url: text // data: any)` is one. The conformance tests load a fix for it
    (`conformance/tests/support/cddl_rb_group_choice.rb`), and the fix is offered upstream.
  - anweiss/cddl rejects every map that uses `~`, so the unwrapping rules are checked with the Ruby tool only.
- **Exactly one of `url` or `data`.** The CDDL requires one of them, but `CatalogEntry`'s trailing `* text => any`
  accepts the other as well, so only the OpenAPI document and the conformance tool reject a result carrying both.
  AI Catalog's own grammar has the same gap.
- **`updatedAt` in JSON.** AI Catalog types `updatedAt` as `tdate`, which is CBOR tag 0, and JSON has no tags. The
  conformance tests read `tdate` as its string when validating JSON.
