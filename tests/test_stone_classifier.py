import numpy as np

from vision.stone_classifier import StoneClassifier


def expected():
    g = np.zeros((8, 8), int)
    g[4, 5] = 1
    g[5, 6] = 2
    return g


def test_default_rules_find_black(warped):
    g = StoneClassifier().classify(warped)
    assert g[4, 5] == 1
    assert (g == 1).sum() == 1          # 흑돌은 정확히 1개
    # 흰 종이 위 흰 돌은 기본 규칙으로는 못 잡는 것이 정상 (캘리브레이션 필요)


def test_calibrated_model_finds_both(warped, tmp_path):
    clf = StoneClassifier()
    clf.fit(warped, expected())
    assert np.array_equal(clf.classify(warped), expected())

    path = tmp_path / 'stones.json'
    clf.save(str(path))
    import json
    clf2 = StoneClassifier(model=json.loads(path.read_text(encoding='utf-8')))
    assert np.array_equal(clf2.classify(warped), expected())
