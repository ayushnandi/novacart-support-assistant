import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.chat.sentiment import score
from app.config import SENTIMENT_NEGATIVE_THRESHOLD

# Ordinary support questions. These carry words VADER reads as negative on their own
# ("damaged", "defective", "cancel"), so they are the ones that produce unwanted
# "shall I get you a human?" offers if the threshold drifts up.
ROUTINE = [
    "how do i track my order?",
    "what is your return policy?",
    "what was my order id again?",
    "can i cancel an order after placing it?",
    "what if my item arrives damaged?",
    "how do i return a defective item?",
    "i want to cancel my subscription",
    "my package is late, where is it?",
    # Negative topic words stacking up - these describe the item, not the customer's mood.
    "how do i return a defective item that arrived damaged?",
    "my order is late and one item is missing",
    "i received the wrong item and the box was damaged",
    "i have a problem with a cancelled order",
]

FRUSTRATED = [
    "this is ridiculous, i have been waiting for two weeks and nobody helps me",
    "this is unacceptable",
    "i am so frustrated with this",
    "worst service ever",
    "my order never arrived and no one has responded",
    "i am fed up with this useless app",
    "your support is pathetic and useless",
]


@pytest.mark.parametrize("message", ROUTINE)
def test_routine_questions_do_not_read_as_frustration(message):
    assert score(message) >= SENTIMENT_NEGATIVE_THRESHOLD, (
        f"{message!r} would wrongly trigger a human offer"
    )


@pytest.mark.parametrize("message", FRUSTRATED)
def test_real_complaints_are_detected(message):
    assert score(message) < SENTIMENT_NEGATIVE_THRESHOLD, (
        f"{message!r} should be recognised as an unhappy customer"
    )
