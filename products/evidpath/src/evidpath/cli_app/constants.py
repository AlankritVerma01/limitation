"""Stable CLI surface text and target-mode wording."""

EXTERNAL_TARGET_HELP = (
    "Customer-owned external endpoint for the selected domain. This is the "
    "primary supported installed-package path. If omitted, Evidpath will try "
    "the product-owned local reference target when it is available in the "
    "current environment."
)
REFERENCE_ARTIFACT_DIR_HELP = (
    "Optional artifact directory override for the product-owned local reference "
    "target. Use this for repo/demo workflows when local reference artifacts "
    "are available, not for customer endpoints."
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
    "to persist in the saved plan when local reference artifacts are available."
)
COMPARE_REFERENCE_TARGET_HELP = (
    "Artifact directory for the product-owned local reference target when it is "
    "available in the current environment."
)
COMPARE_EXTERNAL_TARGET_HELP = "Customer-owned external endpoint for this compare target."
