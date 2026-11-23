// Exercise the same engine used by the page and the frame recorder.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const page = readFileSync(new URL("./reference.html", import.meta.url), "utf8");
const section = (start, end) => page.slice(page.indexOf(start), page.indexOf(end));
const { Pane, defaults, tiny, source, fps } = runInNewContext(
  section("// ENGINE START", "// ENGINE END") + section("const DEFAULTS =", "const STORE =") +
  "({Pane, defaults: DEFAULTS, tiny: PRESETS.tiny, source: buildSource(1), fps: FPS})"
);
const measure = text => [...text].length * 10;
const epsilon = 1e-7;

for (const mode of ["instant", "scrolling"]) {
  test(mode + " keeps rows within bounds and holds finished rows for half a second", () => {
    const pane = new Pane(mode, measure);
    pane.reset({...defaults, ...tiny, H: 150, motionOnly: true}, source);
    let previous = new Map(), departures = 0;
    const holds = new Map();
    for (let frame = 0; frame <= Math.ceil((source.at(-1).transT + 4) * fps); ++frame) {
      pane.step(frame / fps);
      const rows = pane.rows(), next = new Map(rows.map(row => [row.key, row]));
      for (const [key, start] of holds) {
        const old = previous.get(key), row = next.get(key);
        if (!row || Math.abs(row.x - old.x) > epsilon || Math.abs(row.y - old.y) > epsilon ||
            row.text.trimEnd() !== old.text.trimEnd()) {
          assert.ok((frame - start) / fps >= defaults.minHold);
          holds.delete(key);
          ++departures;
        }
      }
      for (const [index, row] of rows.entries()) {
        assert.ok(row.y >= pane.g.pad - epsilon);
        assert.ok(row.y + row.h <= pane.g.foot + epsilon);
        if (index) assert.ok(rows[index - 1].y + rows[index - 1].h <= row.y + epsilon);
        const old = previous.get(row.key);
        if (old) {
          assert.ok(row.y <= old.y + epsilon);
        }
        if (mode === "instant") assert.equal(row.x, 0);
        if (row.phase === "settled" && old?.phase !== "settled") holds.set(row.key, frame);
      }
      previous = next;
    }
    assert.ok(departures > 5);
  });
}

test("scrolling brings an overflowing line into view with bounded, eased steps", () => {
  const caption = {
    id: 1, finishT: 1, transT: 1, zh: "",
    en: "Short. " + "stretched ".repeat(6).trim(),
    updates: [{t: 0, words: [{t: "Short."}]}], tupdates: [],
  };
  const pane = new Pane("scrolling", measure);
  pane.reset({...defaults, motionOnly: true, W: 250}, [caption]);
  let x = 0;
  const steps = [];
  for (let frame = 0; frame <= 2 * fps; ++frame) {
    pane.step(frame / fps);
    const row = pane.rows()[0];
    assert.equal(row.start, 0);
    if (frame >= fps && frame <= fps * 1.2) steps.push(row.x - x);
    x = row.x;
    if (frame === fps * 1.2) assert.ok(measure(row.text) - x <= pane.g.avail);
  }
  assert.ok(steps.filter(step => step > 0).length > 1);
  assert.ok(steps.every(step => step <= defaults.catchupStep));
  assert.ok(Math.max(...steps) > steps.at(-1));
  assert.equal(pane.rows()[0].phase, "settled");
  assert.equal(pane.rows()[0].text, caption.en);
});

test("wrapping preserves offsets and keeps closing punctuation with the preceding unit", () => {
  const pane = new Pane("instant", measure);
  pane.reset({...defaults, W: 120}, []);
  for (const side of [0, 1]) {
    for (const text of ["Second word here.", "報告警告稱沒有人能保證目前採取的任何行動。", "🔴".repeat(30)]) {
      const rows = pane.wrap(text, side);
      assert.equal(rows.join(""), text);
      assert.ok(rows.every(row => !row.startsWith("。") && measure(row.trimEnd()) <= pane.g.avail));
    }
  }
  const chinese = "目前在伊拉克採取的任何行動";
  assert.ok(pane.readingNeed(chinese, 0) >= 0.35 + [...chinese].length / 3.25);
  assert.ok(pane.readingNeed(chinese, 0) > pane.readingNeed(chinese, 1));
});

test("the next caption waits for the last word to paint", () => {
  const text = "Here are the very last words.";
  const pane = new Pane("instant", measure);
  pane.reset(defaults, [
    {id: 0, finishT: 0, transT: 0, en: text, zh: "", updates: [], tupdates: []},
    {id: 1, finishT: 1 / fps, transT: 1, en: "Next.", zh: "", updates: [], tupdates: []},
  ]);
  for (let frame = 0; frame < 6; ++frame) {
    pane.step(frame / fps);
    assert.equal(pane.last, 0);
  }
  assert.equal(pane.rows().find(row => row.id === 0)?.text, text);
  for (let frame = 6; frame < 150; ++frame) pane.step(frame / fps);
  assert.ok(pane.rows().some(row => row.id === 1 && row.text === "Next."));
});

test("track and mode changes retain the latest caption while hiding the selected track", () => {
  const pane = new Pane("scrolling", measure);
  pane.reset({...defaults, motionOnly: true}, source);
  for (let frame = 0; frame <= 409; ++frame) pane.step(frame / fps);
  const last = pane.last;
  assert.ok(pane.rows().some(row => row.id === last && row.side));
  pane.sides[0] = false;
  pane.mode = "instant";
  pane.step(410 / fps);
  assert.equal(pane.last, last);
  assert.ok(pane.rows().length && pane.rows().every(row => row.side));
  assert.ok(pane.rows().some(row => row.id === last));
});
