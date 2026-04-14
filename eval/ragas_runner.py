"""Compute Ragas core RAG metrics for a single sample.

Ragas is an optional dependency: if it's not installed, metric calls
return None, and the aggregator counts those samples as failures for the
affected metric. Production CI runs must install Ragas; unit tests
monkey-patch `score_sample` to avoid paying for LLM-as-judge calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

RagasMetrics = Dict[str, Optional[float]]

METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


def _empty_scores() -> RagasMetrics:
    return {name: None for name in METRIC_NAMES}


class RagasRunner:
    """Lazy wrapper around the Ragas metric suite.

    Initialization is deferred until the first call so that importing
    this module never fails if Ragas is missing.
    """

    def __init__(self, judge_model: Optional[str] = None) -> None:
        self._initialized = False
        self._metrics: Dict[str, Any] = {}
        self._sample_cls: Any = None
        self._judge_model = judge_model or get_settings().eval_llm_judge

    def _initialize(self) -> None:
        if self._initialized:
            return
        try:
            from ragas.dataset_schema import SingleTurnSample
            from ragas.llms import llm_factory
            from ragas.metrics import (
                Faithfulness,
                LLMContextPrecisionWithReference,
                LLMContextRecallWithReference,
                ResponseRelevancy,
            )
        except ImportError as exc:  # pragma: no cover - exercised only when ragas missing
            raise RuntimeError(
                "Ragas is not installed. Install with `pip install ragas>=0.4.0`."
            ) from exc

        evaluator_llm = llm_factory(self._judge_model)
        self._metrics = {
            "faithfulness": Faithfulness(llm=evaluator_llm),
            "answer_relevancy": ResponseRelevancy(llm=evaluator_llm),
            "context_precision": LLMContextPrecisionWithReference(llm=evaluator_llm),
            "context_recall": LLMContextRecallWithReference(llm=evaluator_llm),
        }
        self._sample_cls = SingleTurnSample
        self._initialized = True

    async def score_sample(
        self,
        *,
        user_input: str,
        response: str,
        retrieved_contexts: List[str],
        reference: str,
    ) -> RagasMetrics:
        """Run every Ragas metric on a single sample.

        Failures per metric are logged and stored as None so one broken
        LLM-judge call does not kill the entire run.
        """
        try:
            self._initialize()
        except RuntimeError as exc:
            logger.warning("ragas.unavailable", error=str(exc))
            return _empty_scores()

        sample = self._sample_cls(
            user_input=user_input,
            response=response,
            retrieved_contexts=retrieved_contexts,
            reference=reference,
        )

        scores: RagasMetrics = {}
        for name, metric in self._metrics.items():
            try:
                raw = await metric.single_turn_ascore(sample)
                scores[name] = _safe_float(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ragas.metric_failed", metric=name, error=str(exc)
                )
                scores[name] = None
        return scores


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN check
        return None
    return result
