"""Turkish words as a dictionary lists them (polyglotic-hq 388): the
suffixes a word's guesses take off, and how a name is cut."""

from polyglotic_desktop.core.lexicon import turkish


def before(guesses: tuple[str, ...], first: str, then: str) -> bool:
    return (
        first in guesses
        and then in guesses
        and (guesses.index(first) < guesses.index(then))
    )


def test_turkish_lower_case_keeps_its_dotted_and_dotless_i() -> None:
    """Python's lower case of İ is i with a combining dot, and of I a
    dotted i: "İki" and "Işık" were in no dictionary."""
    assert turkish.lower("İki") == "iki"
    assert turkish.lower("Işık") == "ışık"
    assert turkish.bases("İki")[0] == "iki"
    assert turkish.bases("Işık")[0] == "ışık"


def test_a_verb_is_guessed_as_its_infinitive_under_its_suffixes() -> None:
    """Wiktionary's tables have no participles, verbal nouns or "can":
    verilen, olabilir and olması were missing in the installed app."""
    assert "vermek" in turkish.bases("verilen")  # ver + il + en
    assert "olmak" in turkish.bases("olabilir")  # ol + abil + ir
    assert "olmak" in turkish.bases("olması")  # ol + ma + sı
    assert "gelmek" in turkish.bases("gelmeyebilir")  # gel + me + yebil + ir
    assert "bulunmak" in turkish.bases("bulunmaktadır")  # bulun + mak + ta + dır
    assert "anlamak" in turkish.bases("anlıyor")  # -iyor took anla's a
    assert "kullanmak" in turkish.bases("kullanılmamasından")


def test_a_verb_stem_is_never_guessed_as_written() -> None:
    """A verb's stem as written finds other words: "vardı" (from
    vardı-r) is a form of varmak, to arrive, and "bırak" a conjunction -
    bırakılan is bırakmak's (bırak + ıl + an)."""
    guesses = turkish.bases("vardır")
    assert "vardı" not in guesses and "vardımak" in guesses
    assert before(turkish.bases("bırakılan"), "bırakmak", "bırak")


def test_a_nouns_suffixes_come_off_in_their_order() -> None:
    assert turkish.bases("evlerimizde")[-1] == "ev"  # ev + ler + imiz + de
    assert "dünya" in turkish.bases("dünyadaki")  # dünya + da + ki
    assert "galaksi" in turkish.bases("galaksisine")  # galaksi + si + n + e


def test_a_stem_is_also_tried_as_the_dictionary_writes_it() -> None:
    assert turkish.bases("kitabı") == ("kitab", "kitap")  # p before a vowel
    assert "çocuk" in turkish.bases("çocuğu")
    assert "şehir" in turkish.bases("şehri")  # the vowel it lost


def test_the_least_cut_off_comes_first_and_then_the_likelier_reading() -> None:
    """-dır is "is" before it is a causative: vardır is var (there is), not
    varmak (to arrive). A stem as the dictionary writes it counts a letter
    shorter: budur is bu + dur, not but."""
    assert before(turkish.bases("vardır"), "var", "varmak")
    assert before(turkish.bases("budur"), "bu", "butmak")
    assert before(turkish.bases("kızla"), "kız", "kızıl")


def test_buffer_letters_stand_where_turkish_writes_them() -> None:
    """A case's n stands after a possessive's vowel only (evi-n-de), and
    the y of -yum after a vowel only: köknar (a fir) had been kök (root) +
    n + a + r, and sezyum (caesium) sez (to sense) + yum."""
    assert "kök" not in turkish.bases("köknar")
    assert "sezmek" not in turkish.bases("sezyum")


def test_a_name_is_cut_only_at_its_apostrophe_and_possessive() -> None:
    """Names take their suffixes after an apostrophe; a compound name's
    last word may end in its possessive (Pasifik Okyanusu). Cut no
    further: Roma'da had been rom (rum), Bali'de bal (honey)."""
    assert turkish.bases("Afrika'daki") == ("Afrika",)
    assert turkish.bases("Afrika’daki") == ("Afrika",)
    assert "Okyanus" in turkish.bases("Okyanusu'nda")
    assert "Devlet" in turkish.bases("Devletler'deki")
    assert "Ada" in turkish.bases("Adası'dır")
    assert turkish.bases("Roma'da") == ("Roma",)
    assert turkish.bases("Bali'de") == ("Bali",)
    assert turkish.bases("İsveç'te") == ("İsveç", "isveç")
    assert turkish.name_bases("Atlantik") == ()  # not atlamak, to jump
    assert turkish.name_bases("Okyanusu")[0] == "Okyanus"


def test_a_stem_is_also_tried_with_the_circumflex_the_dictionary_writes() -> None:
    """Captions write imkanı; Wiktionary's headword is imkân (the loop's
    real captions, polyglotic-hq 388)."""
    assert before(turkish.bases("imkanı"), "imkan", "imkân")
    assert turkish.circumflexed("rüzgar") == "rüzgâr"
    assert turkish.circumflexed("ev") == "ev"
