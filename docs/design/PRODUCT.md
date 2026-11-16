# Product

<!-- impeccable:product-schema 1 -->

The desktop app's product record, in the shape Impeccable's `init` writes
(polyglotic-hq 347, 2026-11-15). Written from polyglotic-hq's documents
(TOPICS.md's goal, MVP.md, MARKETING.md, 109's PRINCIPLES.md and STRUCTURE.md,
DOMAIN.md), not from an interview; lines marked *(inferred)* are Claude's
reading of them. The visual system is in [DESIGN.md](DESIGN.md).

## Platform

Windows desktop (Qt Widgets, PySide6); macOS and Linux later. Not one of
Impeccable's platforms: its web detector doesn't apply. The UI lab's design
detector (`tools/ui_lab/design.py`, decision 0140) asks its questions of our
windows instead.

## Users

Language learners who already listen a lot on their PC - games, videos,
streams, calls, lessons - and want to learn from it: Chinese learners abroad
and heritage learners first, then learners of Spanish and Anki users,
Chinese-speaking English learners, Spanish and Vietnamese speakers learning
English (MARKETING.md's order). They use Polyglotic while doing something
else: the captions sit over a game or a call, and every second of attention
the app takes is taken from what they came for.

## Product Purpose

Live captions and translations of what the PC plays (one app, everything,
or the mic), with words you can click for their meaning, the words you keep
hearing gathered for review, a transcript, and Anki export. The server does
the speech and translation; the app captures, detects speech, shows and
keeps the learner's words. Success: a learner listens for ten minutes or
more and looks a word up within their first week, then comes back weekly
(ENGINEERING.md's activation and weekly learner).

## Positioning

Windows already captions speech for free. Polyglotic's difference is the
learning on top of live audio from any app: the word under your cursor, the
words you keep meeting, straight into Anki with the sentence you heard.

## Operating Context

- **Over something else:** caption windows float over full-screen games,
  videos and calls; a click on one must never take the keyboard from the
  game (109: they never take the focus).
- **At a glance:** the newest caption is read in a second, then the eye goes
  back to the game.
- **The main window** (Home, Learning, Words, Settings, Help) is visited
  between sessions: choosing what to caption, the level, the deck, settings.
- Text sizes from Windows' 100 % to 225 % and the app's own Smaller to
  Largest; dark by default, light by choice; three themes (Margin, Glaze,
  Signal); the interface in English, Chinese and other languages.

## Capabilities and Constraints

- **Every action is instant** (108's budgets, gated by the UI lab).
- **Nothing new** (DECISIONS #50): the rebuild does what the app did.
- Captions are the learner's: their size, font, colours and position are
  settings, not the design's.
- Privacy: audio and caption text never logged or written; the lab never
  writes caption text.

## Brand Commitments

091's Margin (agreed): ink on paper, a pink marker, Literata for headings;
the caption windows stay neutral in every theme (098), the brand colours
the main window, the transcripts and the lookup card. Voice: plain-spoken,
fair, open, attentive; the glossary's words (DOMAIN.md: caption, finished
caption, live update, lookup card, transcript, deck, saved word...).

## Evidence on Hand

The lab's made-up recorded conversation; no testimonials, user counts or
reviews exist and none may be invented.

## Product Principles

109's, in order:
1. The captions are readable and never in the way.
2. Every action is instant.
3. One obvious place for everything.
4. Honest and quiet: a state is one line where the learner is looking,
   never a modal, never over a game.
5. Nothing new.

## Accessibility & Inclusion

WCAG 2.2 AA where it applies to a desktop app: contrast measured from the
pixels (4.5:1, 3:1 large text and icons), text never under 12 px at any
text size, every control named and reachable by keyboard in windows that
take the keyboard, targets at least 24 px or spaced (2.5.8), reduced motion
honoured *(inferred from the lab's checks)*.
