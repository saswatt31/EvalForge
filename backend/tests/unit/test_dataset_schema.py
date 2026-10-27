import pytest
from pydantic import ValidationError

from app.schemas.dataset import GoldenQuery


def test_golden_query_accepts_valid_record() -> None:
    query = GoldenQuery(
        question="  What is retrieval augmented generation?  ",
        ground_truth="  A pattern that retrieves documents before generation.  ",
        reference_contexts=["  RAG combines retrieval and generation.  "],
        metadata={"source": "sample"},
    )

    assert query.question == "What is retrieval augmented generation?"
    assert query.ground_truth.startswith("A pattern")
    assert query.reference_contexts == ["RAG combines retrieval and generation."]
    assert query.metadata == {"source": "sample"}


@pytest.mark.parametrize("contexts", [[], [""], ["   "]])
def test_golden_query_rejects_missing_reference_contexts(contexts: list[str]) -> None:
    with pytest.raises(ValidationError):
        GoldenQuery(
            question="Question?",
            ground_truth="Truth",
            reference_contexts=contexts,
        )


def test_golden_query_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        GoldenQuery.model_validate(
            {
                "question": "Question?",
                "ground_truth": "Truth",
                "reference_contexts": ["Context"],
                "groundtruth": "Typo",
            }
        )


def test_golden_query_rejects_blank_question() -> None:
    with pytest.raises(ValidationError):
        GoldenQuery(
            question="   ",
            ground_truth="Truth",
            reference_contexts=["Context"],
        )
