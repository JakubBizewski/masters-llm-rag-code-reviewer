from acr_system.experimental.metrics import bleu_4, rouge_l_f1, meteor_simplified, exact_match


def test_exact_match_normalizes_whitespace_and_case():
    assert exact_match("A  b", "a b")
    assert not exact_match("", "")


def test_bleu_4_is_1_for_identical_text():
    s = "unused import should be removed"
    assert bleu_4(s, s) > 0.99


def test_rouge_l_f1_is_1_for_identical_text():
    s = "consider renaming variable"
    assert rouge_l_f1(s, s) == 1.0


def test_meteor_simplified_reasonable_range():
    c = "remove unused import"
    r = "remove unused imports"
    v = meteor_simplified(c, r)
    assert 0.0 <= v <= 1.0
    assert v > 0.3
