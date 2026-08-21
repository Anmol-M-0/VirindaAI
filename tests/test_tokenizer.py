from marina.core.tokenizer import StreamingSentenceTokenizer


def test_streaming_sentences() -> None:
    tokenizer = StreamingSentenceTokenizer()
    out = list(tokenizer.feed("Hello world. How are"))
    assert out == ["Hello world."]
    assert list(tokenizer.feed(" you?")) == []
    assert list(tokenizer.flush()) == ["How are you?"]
