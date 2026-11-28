"""Content-free explanations for a listening session and an empty caption window."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ports.capture import CaptureIssue


def _tr(text: str) -> str:
    return QApplication.translate("CaptureStatus", text)


def listening_for_speech() -> str:
    return _tr("Listening for speech…")


def chromebook_scope() -> str:
    return _tr(
        "Play sound in a Linux app, such as a Linux browser. ChromeOS tabs and Android apps play outside Linux."
    )


def chromebook_help() -> str:
    return (
        chromebook_scope()
        + " "
        + _tr(
            "For your microphone, open Settings → About ChromeOS → Developers → Linux development environment and turn on “Allow Linux to access your microphone”."
        )
    )


def explanation(issue: CaptureIssue, *, mic: bool) -> str:
    match issue:
        case CaptureIssue.LIBRARY:
            return _tr(
                "Linux audio support is missing. Install {package} to listen."
            ).format(
                package="libpulse0"  # the package's name, not a number to translate
            )
        case CaptureIssue.SERVER:
            return _tr(
                "Polyglotic can’t reach the sound server. Check that PulseAudio or pipewire-pulse is running."
            )
        case CaptureIssue.DENIED:
            return _tr(
                "The sound server denied recording access. Check your audio permissions."
            )
        case CaptureIssue.OUTPUT:
            return _tr(
                "No speaker output is available to record. Check your Linux sound settings."
            )
        case CaptureIssue.MIC:
            return _tr("No microphone is available. Check your Linux sound settings.")
        case CaptureIssue.NO_FRAMES:
            return _tr(
                "No audio data has arrived from this source. Check your Linux sound settings."
            )
        case CaptureIssue.SILENT:
            if mic:
                return _tr(
                    "Your microphone is silent. Check that it’s unmuted and try speaking."
                )
            return _tr(
                "No sound is reaching Polyglotic. Is audio playing on the selected output?"
            )
        case CaptureIssue.OPEN | CaptureIssue.STOPPED:
            return _tr(
                "Recording failed. Check the selected device in your Linux sound settings."
            )
