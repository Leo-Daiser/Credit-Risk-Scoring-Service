# ADR 001: Versioned production model artifact contract

- Status: accepted
- Date: 2026-08-07

## Context

Online API, batch scoring and drift monitoring deserialize the same joblib
bundle. A Python object type check alone does not prove that the artifact has
the feature schema, metadata and reference distributions expected by the
runtime. Previously the API could also override its required features and
minimum input coverage through environment variables while batch scoring used
different validation, allowing one model version to have two input contracts.

The previous model version depended on the source model and selected config
fields, but not on the calibration dataset or every acceptance input. A changed
training parquet could therefore produce a different calibrated bundle with the
same version. Directly writing the final joblib path could also damage the last
working artifact if serialization was interrupted.

## Decision

Production bundles use `bundle_format_version = 1` and contain an
`artifact_inputs` manifest with SHA-256 fingerprints for:

- source model and source metrics;
- baseline model and baseline metrics;
- training parquet used to reproduce train/calibration/evaluation splits;
- canonical feature schema;
- canonical production-model configuration, including the input contract;
- model evaluation/packaging source code;
- pinned runtime dependencies from `requirements.txt`.

`model_version` is deterministically derived from this manifest. A manually
configured version is accepted only when it matches the derived value.

Before serving, the loader validates:

- supported bundle format;
- estimator probability interface;
- complete, unique and disjoint numeric/categorical feature schema;
- required input keys and minimum non-null feature coverage;
- feature count, decision threshold and ordered risk bands;
- required SHA-256 manifest entries;
- consistency between the manifest and deterministic `model_version`;
- reference-statistic feature names.

Bundle and metadata are first written to temporary files. The serving bundle is
replaced only after serialization and metadata writing both succeed. Old-format
bundles are rejected and must be regenerated with
`python -m src.cli prepare-production-model`.

API and batch scoring read required keys and minimum coverage only from the
validated bundle. `MODEL_BUNDLE_PATH` is the common deployment override for
API, batch and monitoring; `configs/service.yaml` remains the offline-job
fallback. Monitoring aligns data to the schema but deliberately does not reject
contract violations because missingness is one of the conditions it measures.

## Consequences

- A version identifies the data, models, config, code and pinned dependencies
  needed to reproduce the calibrated artifact and its acceptance decision.
- A failed serialization does not overwrite the last working bundle.
- Runtime incompatibility fails during bundle loading and therefore makes
  readiness fail instead of producing an invalid prediction.
- One model version has one input contract across online and batch inference.
- Hashing the training parquet adds one sequential file read during packaging.

## Trust boundary and non-goals

The manifest provides identity and accidental-corruption diagnostics; it is not
a digital signature and does not establish artifact provenance. Joblib can
execute Python code during deserialization, so artifacts must still come from a
trusted training pipeline.

An external artifact registry, object storage, signing service or MLflow model
registry is intentionally not introduced in this portfolio MVP. The contract
keeps that migration possible without adding infrastructure that the project
does not currently need.
