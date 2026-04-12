"""Stable CLI surface text and target-mode wording."""

EXTERNAL_TARGET_HELP = (
    "Customer-owned external endpoint for the selected domain. This is the real "
    "customer integration path. If omitted, the product-owned local reference "
    "target is used."
)
REFERENCE_ARTIFACT_DIR_HELP = (
    "Optional artifact directory override for the product-owned local reference "
    "target. Use this for the local demo/onboarding path, not customer endpoints."
)
INTERNAL_MOCK_TARGET_HELP = (
    "Use the internal-only mock target for narrow test/debug runs. This is not "
    "the customer path or the main demo path."
)
PLAN_RUN_EXTERNAL_TARGET_HELP = (
    "Customer-owned external endpoint to persist in the saved plan."
)
PLAN_RUN_REFERENCE_ARTIFACT_DIR_HELP = (
    "Artifact directory override for the product-owned local reference target "
    "to persist in the saved plan."
)
COMPARE_REFERENCE_TARGET_HELP = (
    "Artifact directory for the product-owned local reference target."
)
COMPARE_EXTERNAL_TARGET_HELP = "Customer-owned external endpoint for this compare target."
