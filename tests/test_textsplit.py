from voxstudio.textsplit import pieces, sentences


def test_sentences_split_at_endings_only():
    assert sentences("One two. Three four! Five? Six") == ["One two.", "Three four!", "Five?", "Six"]
    assert sentences('He said "Stop." Then he left.') == ['He said "Stop."', "Then he left."]
    assert sentences("Wait… Then it came.") == ["Wait…", "Then it came."]
    assert sentences("") == [] and sentences("  no ending here ") == ["no ending here"]


def test_abbreviations_initials_numbers_and_marks_do_not_split():
    assert sentences("Dr. Smith met Mrs. Jones at St. Mary's. They talked.") == ["Dr. Smith met Mrs. Jones at St. Mary's.", "They talked."]
    assert sentences("J. K. Rowling wrote it. It sold.") == ["J. K. Rowling wrote it.", "It sold."]
    assert sentences("It cost 3.5 million. Then 4.2 more.") == ["It cost 3.5 million.", "Then 4.2 more."]
    assert sentences("the rover [Pragyan](/pɹˈʌɡ. jɑn/) Rolled out. Then stopped.") == ["the rover [Pragyan](/pɹˈʌɡ. jɑn/) Rolled out.", "Then stopped."]
    assert sentences("Say [go](+2). Then *Stop* now.") == ["Say [go](+2).", "Then *Stop* now."]


def test_pieces_send_the_first_sentence_alone_then_group_the_rest():
    text = "This is the first sentence. " + " ".join(f"Sentence number {i} is here." for i in range(2, 30))
    out = pieces(text)
    assert out[0] == "This is the first sentence." and all(len(p) <= 240 for p in out[1:]) and len(out) < 8
    assert " ".join(out) == text
    assert pieces("Wait. Now go there quickly. Then stop.") == ["Wait. Now go there quickly.", "Then stop."]
    assert pieces("Just one line") == ["Just one line"] and pieces("") == []
