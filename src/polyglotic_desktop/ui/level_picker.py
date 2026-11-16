"""The level picker: about how many words do you know? - asked once when a
language is added on Learning, and by "Change your level" any time after
(polyglotic-hq 323; before it, an HSK level or an English frequency band).

One question, a few choices in plain words with the number
(the new interface's `views.known_words`, handed over by `main`: `ui`
doesn't import it): for Chinese each number is an HSK 3.0 level
too, named beside it; "Not sure" takes a middle one. The most common
words up to the choice count as known (`Vocabulary.set_known_words`); the
learner's own statuses are kept. Cancel leaves the level as it was.
"""

from collections.abc import Sequence
from typing import Protocol

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui.widgets import TextDialog


class Choice(Protocol):
    """ "About `known` words" (`views.known_words.Choice`)."""

    @property
    def known(self) -> int: ...

    @property
    def level(self) -> str:
        """The syllabus level that is the same line ("3": HSK 3), or ""."""
        ...

    @property
    def or_more(self) -> bool: ...


class LevelPicker(TextDialog):
    def __init__(
        self,
        language: str,
        offered: Sequence[Choice],
        not_sure: int,
        chosen: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """`language`: the language learned, as the interface names it;
        `offered`: its choices, fewest words first; `not_sure`: the number
        "Not sure" takes; `chosen`: the index of the choice the picker
        opens on - None, "Not sure" (no level set yet)."""
        super().__init__(parent)
        self.setObjectName("LevelPicker")
        self.setWindowTitle(self.tr("Words you know"))
        self.setMinimumWidth(580)  # the note in three lines at 150 % text
        self._not_sure = not_sure
        self._choices = tuple(offered)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        title = QLabel(
            self.tr("About how many {language} words do you know?").format(
                language=language
            )
        )
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        intro = QLabel(
            self.tr(
                "The most common words up to here count as known, the next ones "
                "are pointed out, and rarer ones are left alone. Nothing is "
                "tested: change it any time, and a click on any word corrects it."
            )
        )
        intro.setObjectName("Dim")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        column = QVBoxLayout()
        column.setSpacing(2)
        layout.addLayout(column)
        self._group = QButtonGroup(self)
        for n, choice in enumerate(self._choices):
            button = QRadioButton(self._label(choice))
            button.setObjectName(f"level.{choice.known}")
            self._group.addButton(button, n)
            column.addWidget(button)
        self.not_sure = QRadioButton(
            self.tr("Not sure - start at about {count}").format(
                count=QLocale().toString(not_sure)
            )
        )
        self.not_sure.setObjectName("level.not_sure")
        self._group.addButton(self.not_sure, len(self._choices))
        column.addWidget(self.not_sure)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.choose(chosen)

    def _label(self, choice: Choice) -> str:
        if choice.known == 0:
            return self.tr("I'm just starting")
        count = QLocale().toString(choice.known)
        if choice.level:
            return self.tr("About {count} - HSK {level}").format(
                count=count, level=choice.level
            )
        if choice.or_more:
            return self.tr("{count} or more").format(count=count)
        return self.tr("About {count}").format(count=count)

    def choose(self, index: int | None) -> None:
        """Checks the choice at `index` (None: "Not sure")."""
        button = self._group.button(len(self._choices) if index is None else index)
        (button or self.not_sure).setChecked(True)

    def known(self) -> int:
        """The number of words chosen; "Not sure" is its middle one."""
        index = self._group.checkedId()
        if 0 <= index < len(self._choices):
            return self._choices[index].known
        return self._not_sure
