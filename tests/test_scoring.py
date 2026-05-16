from arxiv_daily.scoring import KeywordRule, score_text


def test_score_text_matches_includes_and_excludes_noise():
    rules = [
        KeywordRule(1, "Robotics", 2.0, "robot", "include"),
        KeywordRule(2, "VLA", 3.0, "vision-language-action", "include"),
        KeywordRule(1, "Robotics", 2.0, "chatbot", "exclude"),
    ]

    result = score_text(
        "Vision-Language-Action Robot Policy",
        "A benchmark for embodied robot manipulation.",
        rules,
    )
    assert result.score == 5.0
    assert result.is_relevant

    noisy = score_text("A chatbot benchmark", "No robot hardware is used.", rules)
    assert noisy.excluded_keywords
    assert not noisy.is_relevant

