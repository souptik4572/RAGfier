from __future__ import annotations

from eval.metrics.citation_coverage import citation_coverage_score
from eval.metrics.decline_accuracy import decline_accuracy_score, is_decline_response
from eval.metrics.latency_compliance import latency_compliance_score


class TestCitationCoverage:
    def test_fully_cited_answer_scores_one(self) -> None:
        response = (
            "The liability cap shall not exceed one million dollars [SOURCE_1]. "
            "The limitation applies to both direct and indirect damages [SOURCE_2]."
        )
        assert citation_coverage_score(response) == 1.0

    def test_no_citations_scores_zero(self) -> None:
        response = (
            "The liability cap shall not exceed one million dollars. "
            "The limitation applies to direct and indirect damages."
        )
        assert citation_coverage_score(response) == 0.0

    def test_decline_response_scores_one(self) -> None:
        response = "I don't have enough information in the available documents to answer this."
        assert citation_coverage_score(response) == 1.0

    def test_partial_coverage(self) -> None:
        response = (
            "The liability cap shall not exceed one million dollars [SOURCE_1]. "
            "The limitation applies to both direct and indirect damages."
        )
        score = citation_coverage_score(response)
        assert 0.0 < score < 1.0

    def test_empty_response_is_zero(self) -> None:
        assert citation_coverage_score("") == 0.0
        assert citation_coverage_score("   ") == 0.0


class TestDeclineAccuracy:
    def test_correct_decline_on_unanswerable(self) -> None:
        response = "I don't have enough information in the available documents."
        assert decline_accuracy_score(response, is_unanswerable=True) == 1.0

    def test_incorrect_answer_on_unanswerable(self) -> None:
        response = "The CEO's favourite colour is blue [SOURCE_1]."
        assert decline_accuracy_score(response, is_unanswerable=True) == 0.0

    def test_correct_answer_on_answerable(self) -> None:
        response = "The liability cap is one million dollars [SOURCE_1]."
        assert decline_accuracy_score(response, is_unanswerable=False) == 1.0

    def test_incorrect_decline_on_answerable(self) -> None:
        response = "I cannot find this information in the available documents."
        assert decline_accuracy_score(response, is_unanswerable=False) == 0.0

    def test_decline_detection_is_case_insensitive(self) -> None:
        assert is_decline_response("I DON'T HAVE ENOUGH INFORMATION")


class TestLatencyCompliance:
    def test_within_budget(self) -> None:
        assert latency_compliance_score(3200, budget_ms=5000) == 1.0

    def test_at_budget_boundary(self) -> None:
        assert latency_compliance_score(5000, budget_ms=5000) == 1.0

    def test_over_budget(self) -> None:
        assert latency_compliance_score(6200, budget_ms=5000) == 0.0

    def test_none_counts_as_non_compliant(self) -> None:
        assert latency_compliance_score(None, budget_ms=5000) == 0.0
