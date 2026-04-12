"""Parser construction for the public interaction-harness CLI."""

from __future__ import annotations

import argparse

from ..domain_registry import list_public_domain_definitions
from ..generation_support import (
    DEFAULT_POPULATION_PROVIDER_MODEL,
    DEFAULT_PROVIDER_PROFILE,
    DEFAULT_SCENARIO_PROVIDER_MODEL,
    DEFAULT_SEMANTIC_PROVIDER_MODEL,
    list_provider_profiles,
)
from .constants import (
    COMPARE_EXTERNAL_TARGET_HELP,
    COMPARE_REFERENCE_TARGET_HELP,
    EXTERNAL_TARGET_HELP,
    INTERNAL_MOCK_TARGET_HELP,
    PLAN_RUN_EXTERNAL_TARGET_HELP,
    PLAN_RUN_REFERENCE_ARTIFACT_DIR_HELP,
    REFERENCE_ARTIFACT_DIR_HELP,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the supported interaction-harness workflows."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Run interaction-harness workflows through the shared CLI.\n\n"
            "Recommended v1 paths:\n"
            "- `run-swarm --domain recommender --target-url ... --brief ...`: one-command intent-driven swarm run\n"
            "- `plan-run --workflow run-swarm|compare|audit ...` then `execute-plan --run-plan-path ...`: explicit plan-first workflow\n"
            "- `audit --domain recommender`: product-owned local reference target or a customer-owned external endpoint\n"
            "- `check-target --domain recommender --target-url ...`: validate a customer endpoint before a full run\n"
            "- `compare --domain recommender`: product-owned reference artifacts or customer-owned external URLs\n"
            "- `generate-scenarios --domain recommender` / `generate-population --domain recommender`\n"
            "- `serve-reference --domain recommender`: explicit local reference-service workflow\n\n"
            "AI-backed generation expands coverage. The runtime and regression core stay deterministic."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    _build_audit_parser(subparsers)
    _build_run_swarm_parser(subparsers)
    _build_plan_run_parser(subparsers)
    _build_execute_plan_parser(subparsers)
    _build_check_target_parser(subparsers)
    _build_compare_parser(subparsers)
    _build_generate_scenarios_parser(subparsers)
    _build_generate_population_parser(subparsers)
    _build_serve_reference_parser(subparsers)
    return parser


def _build_audit_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "audit",
        help="Run one domain audit and write the standard artifact bundle.",
        description=(
            "Run one domain audit against the product-owned local reference target "
            "or a customer-owned external endpoint."
        ),
    )
    parser.set_defaults(handler_name="audit")
    _add_shared_run_arguments(parser)
    _add_direct_target_arguments(parser, planned=False)
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name override for the audit.",
    )
    parser.add_argument(
        "--include-slice-membership",
        action="store_true",
        help="Include full discovered-slice membership in results.json.",
    )
    return parser


def _build_run_swarm_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "run-swarm",
        help="Generate coverage from one brief, run the swarm, and write one audit bundle.",
        description=(
            "Generate scenarios and a saved swarm from one brief, then run a domain audit "
            "against the product-owned local reference target or a customer-owned external endpoint."
        ),
    )
    parser.set_defaults(handler_name="run_swarm")
    _add_run_swarm_arguments(parser)
    _add_direct_target_arguments(parser, planned=False)
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name override for the audit.",
    )
    return parser


def _build_compare_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "compare",
        help="Compare baseline and candidate domain targets across reruns.",
        description=(
            "Run regression compare mode for product-owned reference artifacts or "
            "customer-owned external URLs."
        ),
    )
    parser.set_defaults(handler_name="compare")
    _add_shared_run_arguments(parser)
    parser.add_argument(
        "--brief",
        default=None,
        help="Optional shared brief used to plan shared coverage for both baseline and candidate.",
    )
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help=f"Baseline {COMPARE_REFERENCE_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--baseline-url",
        default=None,
        help=f"Baseline {COMPARE_EXTERNAL_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help=f"Candidate {COMPARE_REFERENCE_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--candidate-url",
        default=None,
        help=f"Candidate {COMPARE_EXTERNAL_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--rerun-count",
        type=int,
        default=3,
        help="Number of reruns per target.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Display label for the baseline target.",
    )
    parser.add_argument(
        "--candidate-label",
        default="candidate",
        help="Display label for the candidate target.",
    )
    parser.add_argument(
        "--policy-mode",
        default="default",
        choices=("default", "report_only"),
        help="Regression policy mode.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Coverage-generation mode used when compare plans shared generated coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help="Named AI profile used when compare plans provider-backed shared coverage.",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of generated scenarios when compare plans shared scenario coverage.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Optional explicit final swarm size when compare plans shared swarm coverage.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic swarm selection in compare planning.",
    )
    return parser


def _build_plan_run_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "plan-run",
        help="Create a durable run plan without executing it.",
        description=(
            "Create a reusable `run_plan.json` for `run-swarm`, `compare`, or `audit` "
            "without running the workflow yet."
        ),
    )
    parser.set_defaults(handler_name="plan_run")
    parser.add_argument(
        "--workflow",
        required=True,
        choices=("run-swarm", "compare", "audit"),
        help="Workflow to plan.",
    )
    _add_shared_execution_arguments(parser)
    parser.add_argument(
        "--brief",
        default=None,
        help="Brief used to plan run-swarm coverage or optional shared compare coverage.",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        help="Optional built-in scenario selection used by compare or audit plans without a shared brief.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Optional saved scenario-pack path to lock into the run plan.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Optional saved population-pack path to lock into the run plan.",
    )
    parser.add_argument(
        "--include-slice-membership",
        action="store_true",
        help="Include full discovered-slice membership in the realized results when the plan executes.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Coverage-generation mode used for planned fresh coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help="Named AI profile used for planned provider-backed coverage.",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Planned generated scenario count.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Planned final swarm size when the plan generates a new swarm.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Planned candidate count before deterministic swarm selection.",
    )
    _add_direct_target_arguments(parser, planned=True)
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name to persist in a `run-swarm` or `audit` plan.",
    )
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help=f"Baseline {COMPARE_REFERENCE_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--baseline-url",
        default=None,
        help=f"Baseline {COMPARE_EXTERNAL_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help=f"Candidate {COMPARE_REFERENCE_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--candidate-url",
        default=None,
        help=f"Candidate {COMPARE_EXTERNAL_TARGET_HELP.lower()}",
    )
    parser.add_argument(
        "--rerun-count",
        type=int,
        default=3,
        help="Planned rerun count for compare.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Display label for the compare baseline target.",
    )
    parser.add_argument(
        "--candidate-label",
        default="candidate",
        help="Display label for the compare candidate target.",
    )
    parser.add_argument(
        "--policy-mode",
        default="default",
        choices=("default", "report_only"),
        help="Regression policy mode to persist in a compare plan.",
    )
    return parser


def _build_execute_plan_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "execute-plan",
        help="Execute one saved run plan deterministically.",
        description=(
            "Load a saved `run_plan.json` and execute it without running a fresh planning pass."
        ),
    )
    parser.set_defaults(handler_name="execute_plan")
    parser.add_argument(
        "--run-plan-path",
        required=True,
        help="Path to the saved `run_plan.json` to execute.",
    )
    return parser


def _build_check_target_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "check-target",
        help="Validate one external target before running a full audit.",
        description=(
            "Run a lightweight contract check against a customer-owned external target "
            "for the selected domain."
        ),
    )
    parser.set_defaults(handler_name="check_target")
    _add_domain_argument(parser)
    parser.add_argument(
        "--target-url",
        required=True,
        help="Customer-owned external endpoint to validate.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=2.0,
        help="Per-request timeout used during the target check.",
    )
    return parser


def _build_generate_scenarios_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "generate-scenarios",
        help="Generate and save a structured scenario pack for one domain.",
        description=(
            "Generate a structured scenario pack for one domain. Use `provider` for "
            "the recommended AI-authored coverage workflow and `fixture` for deterministic CI/demo runs. "
            "The default `fast` AI profile favors lower cost and latency."
        ),
    )
    parser.set_defaults(handler_name="generate_scenarios")
    _add_domain_argument(parser)
    parser.add_argument(
        "--brief",
        required=True,
        help="Short brief used to generate the scenario pack.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated pack.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Optional explicit output path for the generated scenario pack.",
    )
    parser.add_argument(
        "--mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Generation mode. `provider` is recommended for richer launch-grade coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used when `--mode provider` and no explicit `--model` override is set."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional explicit provider model override for scenario generation. "
            f"Defaults to `{DEFAULT_SCENARIO_PROVIDER_MODEL}` through the selected AI profile."
        ),
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of scenarios to generate.",
    )
    return parser


def _build_generate_population_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "generate-population",
        help="Generate and save a structured population pack for one domain.",
        description=(
            "Generate a structured population pack for one domain. Use `provider` for "
            "the recommended AI-authored swarm workflow and `fixture` for deterministic CI/demo runs. "
            "The default `fast` AI profile favors lower cost and latency."
        ),
    )
    parser.set_defaults(handler_name="generate_population")
    _add_domain_argument(parser)
    parser.add_argument(
        "--brief",
        required=True,
        help="Short brief used to generate the population pack.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated pack.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Optional explicit output path for the generated population pack.",
    )
    parser.add_argument(
        "--mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Generation mode. `provider` is recommended for richer launch-grade coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used when `--mode provider` and no explicit `--model` override is set."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional explicit provider model override for population generation. "
            f"Defaults to `{DEFAULT_POPULATION_PROVIDER_MODEL}` through the selected AI profile."
        ),
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Optional explicit final swarm size.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic diversity filtering.",
    )
    return parser


def _build_serve_reference_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "serve-reference",
        help="Start a local reference service for one domain and print its URL.",
        description="Start the product-owned local reference service for one domain when supported.",
    )
    parser.set_defaults(handler_name="serve_reference")
    _add_domain_argument(parser)
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help="Optional artifact directory override for the product-owned local reference service.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind for the local reference service.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind for the local reference service. Use `0` for any free port.",
    )
    return parser


def _add_shared_run_arguments(parser: argparse.ArgumentParser) -> None:
    _add_shared_execution_arguments(parser)
    parser.add_argument(
        "--scenario",
        default="all",
        help="Optional built-in scenario selection for the chosen domain. Use `all` for all built-ins.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Saved scenario-pack path used for the run.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Saved population-pack path used for the run.",
    )


def _add_shared_execution_arguments(parser: argparse.ArgumentParser) -> None:
    _add_domain_argument(parser)
    parser.add_argument("--seed", type=int, default=0, help="Seed for deterministic rollouts.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated artifact bundle.",
    )
    parser.add_argument(
        "--semantic-mode",
        default="off",
        choices=("off", "fixture", "provider"),
        help=(
            "Optional advisory semantic interpretation mode. Use `provider` for "
            "richer explanations; the runtime and regression core stay deterministic."
        ),
    )
    parser.add_argument(
        "--semantic-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used when `--semantic-mode provider` and no explicit "
            "`--semantic-model` override is set."
        ),
    )
    parser.add_argument(
        "--semantic-model",
        default=None,
        help=(
            "Optional explicit provider model override for semantic interpretation. "
            f"Defaults to `{DEFAULT_SEMANTIC_PROVIDER_MODEL}` through the selected semantic profile."
        ),
    )


def _add_run_swarm_arguments(parser: argparse.ArgumentParser) -> None:
    _add_shared_execution_arguments(parser)
    parser.add_argument(
        "--brief",
        required=True,
        help="Short brief used to generate scenarios and the saved swarm for this run.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Optional explicit saved scenario-pack path to reuse for this run.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Optional explicit saved population-pack path to reuse for this run.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Coverage-generation mode for both scenario and swarm generation.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used for both scenario and swarm generation when provider "
            "generation is selected and no explicit model override is set."
        ),
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of generated scenarios when a saved scenario pack is not provided.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Optional explicit final swarm size when a saved population pack is not provided.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic swarm selection.",
    )


def _add_direct_target_arguments(
    parser: argparse.ArgumentParser,
    *,
    planned: bool,
) -> None:
    parser.add_argument(
        "--target-url",
        default=None,
        help=PLAN_RUN_EXTERNAL_TARGET_HELP if planned else EXTERNAL_TARGET_HELP,
    )
    parser.add_argument(
        "--reference-artifact-dir",
        default=None,
        help=(
            PLAN_RUN_REFERENCE_ARTIFACT_DIR_HELP
            if planned
            else REFERENCE_ARTIFACT_DIR_HELP
        ),
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help=INTERNAL_MOCK_TARGET_HELP,
    )


def _add_domain_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--domain",
        required=True,
        choices=list_public_domain_definitions(),
        help="Supported domain for this command.",
    )
