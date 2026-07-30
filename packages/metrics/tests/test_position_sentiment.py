from geo_metrics import position_bucket, position_score, score_sentiment, is_recommended


def test_position_buckets():
    body = "a" * 90
    assert position_bucket(body, 10) == "head"
    assert position_bucket(body, 45) == "middle"
    assert position_bucket(body, 80) == "tail"
    assert position_score("head") == 1.0
    assert position_score(None) == 0.0


def test_sentiment():
    s = score_sentiment("这家公司非常专业靠谱，高质量服务")
    assert s.label == "positive"
    s2 = score_sentiment("体验很差，不推荐，避雷")
    assert s2.label == "negative"


def test_recommend():
    text = "综合来看，我推荐 土巴兔 作为首选平台。"
    assert is_recommended(text, ["土巴兔"]) is True
    assert is_recommended("今天天气好", ["土巴兔"]) is False
