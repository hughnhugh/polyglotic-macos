"""Deleting the learner's learning data: from our server, and - only if they
confirm that too - from this PC.

DOMAIN.md, "Data and privacy": learning data on the server is the learner's
to see and delete. The server's copy goes by protocol.md's
`learning_delete`, which names no language: every language's goes. The
copy on this PC (statuses, saved words with their sentences, exposure
counts) is theirs as well, so deleting it is a separate, explicit choice -
off until ticked - and covers every language whose learning data is open
(each its own file, project 043; DECISIONS #135, polyglotic-hq 306), with
any copies of those files set aside after damage (polyglotic-hq 206):
when there are some, the dialog says how many go with them (207) - under
the box, while it's ticked (223). The dialog only
asks; `main` sends the request (`DataExchange.delete_learning`) and, once the server
answers, deletes the local copy if asked (`Vocabulary.delete_learning_data`).
Every string goes through `tr()`.
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui.os_words import pc_or_mac

BOX_INDENT = 24
"""The set-aside line's indent: under the box's words, not its square."""


class DeleteLearningDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, set_aside: int = 0) -> None:
        """`set_aside`: how many copies of the learning data are set aside
        on this PC, every open language's - deleted with it."""
        super().__init__(parent)
        self.setObjectName("DeleteLearningDialog")
        self.setWindowTitle(self.tr("Delete your learning data"))
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        title = QLabel(self.tr("Delete your learning data from our server?"))
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        text = QLabel(
            pc_or_mac(
                self.tr(
                    "We'll delete the words you looked up, saved and marked, and any "
                    "exposure counts you shared, in every language you learn. Your "
                    "other PCs keep their own copies until you delete them there too."
                ),
                self.tr(
                    "We'll delete the words you looked up, saved and marked, and any "
                    "exposure counts you shared, in every language you learn. Your "
                    "other computers keep their own copies until you delete them there "
                    "too."
                ),
            )
        )
        text.setObjectName("Dim")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.on_this_pc = QCheckBox(
            pc_or_mac(
                self.tr(
                    "Also delete it from this PC, in every language you're learning "
                    "- your word statuses, saved words and how often you heard each "
                    "word"
                ),
                self.tr(
                    "Also delete it from this Mac, in every language you're learning - "
                    "your word statuses, saved words and how often you heard each word"
                ),
            )
        )
        self.on_this_pc.setObjectName("delete.on_this_pc")
        self.on_this_pc.setChecked(False)
        layout.addWidget(self.on_this_pc)
        self.set_aside: QLabel | None = None
        if set_aside:
            # said under the box, and only while it's ticked: unticked, nothing
            # on this PC is deleted, the copies included (polyglotic-hq 223)
            self.set_aside = QLabel(
                pc_or_mac(
                    self.tr(
                        "This also deletes the %Ln copy(s) of your learning data set "
                        "aside on this PC when it was found damaged.",
                        "",
                        set_aside,
                    ),
                    self.tr(
                        "This also deletes the %Ln copy(s) of your learning data set "
                        "aside on this Mac when it was found damaged.",
                        "",
                        set_aside,
                    ),
                )
            )
            self.set_aside.setObjectName("Dim")
            self.set_aside.setWordWrap(True)
            self.set_aside.setContentsMargins(BOX_INDENT, 0, 0, 0)
            self.set_aside.setVisible(False)
            self.on_this_pc.toggled.connect(self._say_set_aside)
            layout.addWidget(self.set_aside)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Delete"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _say_set_aside(self, ticked: bool) -> None:
        """The copies' line shown or not, and the dialog as tall as it now
        needs: Qt doesn't grow a shown window for a wrapped line that
        appears in it - the title and the paragraph were squeezed instead."""
        if self.set_aside is None:
            return
        self.set_aside.setVisible(ticked)
        layout = self.layout()
        if layout is None or not self.isVisible():
            return
        layout.activate()
        needed = layout.totalHeightForWidth(self.width())
        if needed > 0 and needed != self.height():
            self.resize(self.width(), needed)

    def delete_on_this_pc(self) -> bool:
        return self.on_this_pc.isChecked()
