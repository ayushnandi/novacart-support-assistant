from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

# VADER's lexicon is tuned for general prose, so it misreads support complaints: it scored
# "this is ridiculous, i have been waiting two weeks and nobody helps me" as +0.03, because
# "helps" is a positive word and "ridiculous" barely registers. These are the complaint terms
# that actually signal an unhappy customer, weighted on VADER's -4..+4 scale.
_SUPPORT_LEXICON = {
    "ridiculous": -2.5,
    "unacceptable": -2.8,
    "frustrated": -2.5,
    "frustrating": -2.5,
    "useless": -2.5,
    "pathetic": -2.8,
    "disappointed": -2.0,
    "ignored": -2.0,
    "waiting": -1.2,
    "nobody": -1.5,
    "noone": -1.5,
    "never": -1.5,
    "refuse": -2.0,
    "refused": -2.0,
    "scam": -3.0,
    "cheated": -3.0,
    "fed up": -2.8,
}

# The other half of the problem: words that describe the *item*, not the customer's mood.
# VADER scores "damaged" and "defective" at -0.44 each, so an ordinary question like "how do
# i return a defective item that arrived damaged?" stacks them into -0.70 and looks angrier
# than "this is unacceptable". Damped to near-neutral so only emotional language moves the
# score - which is what we are actually trying to measure.
_TOPIC_LEXICON = {
    "damaged": -0.5,
    "damage": -0.5,
    "defective": -0.5,
    "broken": -0.5,
    "faulty": -0.5,
    "missing": -0.5,
    "delayed": -0.5,
    "late": -0.5,
    "wrong": -0.5,
    "cancel": 0.0,
    "cancelled": 0.0,
    "cancellation": 0.0,
    "problem": -0.5,
    "issue": -0.5,
    "complaint": -0.5,
}

_analyzer.lexicon.update(_TOPIC_LEXICON)
_analyzer.lexicon.update(_SUPPORT_LEXICON)  # complaint words win over topic damping


def score(text: str) -> float:
    return _analyzer.polarity_scores(text)["compound"]
