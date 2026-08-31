"""Unit tests for critic review schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aiswarm.schemas.review import (
    FlawSeverity,
    ReviewFlaw,
    ArchitectureReview,
    PerformanceReview,
    SecurityReview,
)


class TestFlawSeverity:
    def test_has_five_levels(self) -> None:
        assert len(FlawSeverity) == 5

    def test_critical_is_a_member(self) -> None:
        assert FlawSeverity.CRITICAL == "CRITICAL"


class TestReviewFlaw:
    def test_minimal_construction(self) -> None:
        flaw = ReviewFlaw(
            severity=FlawSeverity.HIGH,
            category="security",
            description="SQL injection",
            mandatory_fix="use parameterized queries",
        )
        assert flaw.file_path is None

    def test_references_default_empty(self) -> None:
        flaw = ReviewFlaw(
            severity=FlawSeverity.LOW,
            category="style",
            description="x",
            mandatory_fix="y",
        )
        assert flaw.references == []

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReviewFlaw(severity=FlawSeverity.LOW, category="style")  # type: ignore[call-arg]


class TestArchitectureReview:
    def test_scores_bounded_0_to_10(self) -> None:
        with pytest.raises(ValidationError):
            ArchitectureReview(
                decision="APPROVE",
                production_ready=True,
                solid_compliance=True,
                separation_of_concerns=True,
                coupling_score=11,
                cohesion_score=5,
                abstraction_quality=5,
                overall_score=80,
            )

    def test_overall_score_bounded_0_to_100(self) -> None:
        with pytest.raises(ValidationError):
            ArchitectureReview(
                decision="APPROVE",
                production_ready=True,
                solid_compliance=True,
                separation_of_concerns=True,
                coupling_score=5,
                cohesion_score=5,
                abstraction_quality=5,
                overall_score=101,
            )

    def test_valid_review_constructs(self) -> None:
        r = ArchitectureReview(
            decision="APPROVE",
            production_ready=True,
            solid_compliance=True,
            separation_of_concerns=True,
            coupling_score=3,
            cohesion_score=8,
            abstraction_quality=7,
            overall_score=85,
        )
        assert r.fatal_flaw is None
        assert r.flaws == []

    def test_timestamp_auto_populated(self) -> None:
        r = ArchitectureReview(
            decision="REJECT",
            production_ready=False,
            solid_compliance=False,
            separation_of_concerns=False,
            coupling_score=9,
            cohesion_score=2,
            abstraction_quality=2,
            overall_score=20,
        )
        assert r.timestamp is not None


class TestPerformanceReview:
    def test_boolean_flags_required(self) -> None:
        r = PerformanceReview(
            decision="APPROVE",
            production_ready=True,
            has_algorithmic_issues=False,
            has_memory_issues=False,
            has_io_bottlenecks=False,
            has_concurrency_issues=False,
            overall_score=90,
        )
        assert r.has_algorithmic_issues is False

    def test_optimization_suggestions_default_empty_list(self) -> None:
        r = PerformanceReview(
            decision="APPROVE",
            production_ready=True,
            has_algorithmic_issues=False,
            has_memory_issues=False,
            has_io_bottlenecks=False,
            has_concurrency_issues=False,
            overall_score=90,
        )
        assert r.optimization_suggestions == []


class TestSecurityReview:
    def test_cve_references_default_empty(self) -> None:
        r = SecurityReview(
            decision="REJECT",
            production_ready=False,
            has_injection_risk=True,
            has_auth_issues=False,
            has_data_exposure=False,
            has_dependency_risk=False,
            has_crypto_issues=False,
            has_input_validation=False,
            overall_score=10,
            fatal_flaw="SQL injection in query builder",
        )
        assert r.cve_references == []
        assert r.fatal_flaw is not None

    def test_can_carry_cve_references(self) -> None:
        r = SecurityReview(
            decision="REJECT",
            production_ready=False,
            has_injection_risk=False,
            has_auth_issues=False,
            has_data_exposure=False,
            has_dependency_risk=True,
            has_crypto_issues=False,
            has_input_validation=True,
            overall_score=30,
            cve_references=["CVE-2024-1234"],
        )
        assert "CVE-2024-1234" in r.cve_references
