# Evidence report layout

The PDF export starts with a one-page research brief: a plain-language assessment, recorded coverage, interpretation and a concrete next action. Findings show their evidence status, impact and human review separately. Experiment outputs use labeled metric tables and retain their recorded numeric scales; changed-protocol runs stay distinct from original execution.

When zero supported checks complete, the report says **Not enough evidence to verify**. Extracted statements are never treated as independently verified claims. A passed-check assessment is limited to completed checks, and superseded findings do not drive the current summary.

The following pages contain findings and coverage, measured experiments when available, categorized source quotations with page/line/cell anchors, and an audit trail. Long quotations are explicitly labeled as excerpts; full records remain in JSON and the evidence ZIP. Unreadable source characters are marked rather than guessed. Source hashes, repository commits and versioned human decisions retain provenance.

Uploaded-case reports generated for local review belong in `output/pdf/`, which is excluded from Git. The same renderer is used by the normal PDF endpoint and the PDF included in evidence bundles.
