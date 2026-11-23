// Run the frozen 686 engine in Node. Chromium supplies Canvas text metrics and
// photographs the original page. Neither the app nor its renderer is imported.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { runInNewContext } from "node:vm";

import { captionFontCss } from "./fonts.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const [destination, preset = "medium", mode = "instant", timelinePath] = process.argv.slice(2);
if (!destination || !["instant", "scrolling"].includes(mode)) {
  throw Error("Usage: node reference.mjs OUTPUT tiny|small|medium|large|narrow instant|scrolling [timeline.json]");
}
const out = resolve(destination);
mkdirSync(out, {recursive: true});
const page = readFileSync(join(here, "reference.html"), "utf8");
const engine = page.slice(page.indexOf("// ENGINE START"), page.indexOf("// ENGINE END"));
const defaults = page.slice(page.indexOf("const DEFAULTS ="), page.indexOf("const STORE ="));
assert(engine.startsWith("// ENGINE START") && defaults.includes("PRESETS"));
const fixture = timelinePath ? JSON.parse(readFileSync(timelinePath, "utf8")) : null;
const scenario = fixture && !Array.isArray(fixture) ? fixture : null;
const recorded = Array.isArray(fixture) ? fixture : scenario?.source;
const {FPS, DT, LAT, settings, source} = runInNewContext(
  engine + defaults + `
    if (!PRESETS[preset]) throw Error("Unknown preset " + preset);
    ({FPS, DT, LAT, settings: {...DEFAULTS, ...PRESETS[preset]}, source: recorded || buildSource(rate)})
  `, {preset, recorded, rate: scenario?.settings?.rate ?? 1});
Object.assign(settings, scenario?.settings, {motionOnly: !process.env.VIDEO_PACED});
if (scenario?.appFaces) settings.fonts =
  scenario.appFaces.map((face, side) => (side ? settings.transPx : settings.origPx) + "px " + JSON.stringify(face));
const lastFrame = Math.round((Math.ceil((source.at(-1).transT + 3.5) * 10) / 10) * FPS);
const keyframes = scenario?.keyframes ?? [...new Set([source[0].updates[0]?.t ?? source[0].finishT,
  source[0].finishT + settings.lift / 2000,
  source[1]?.finishT - DT, source[1]?.finishT + settings.lift / 2000]
  .filter(Number.isFinite).map(t => Math.round(t * FPS)))];
if (process.env.EXTRA_FRAME) keyframes.push(Number(process.env.EXTRA_FRAME));
const fontCss = await captionFontCss();
const scratch = mkdtempSync(join(out, "browser-"));
const html = join(scratch, "measure.html");
// Collect ink from the same full-row shaping used on the page.
function wordInk(text, font, ctx) {
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const words = Array.from(text.matchAll(/[\u3400-\u9fff]|[^\s\u3400-\u9fff]+/gu), match => {
    const box = metrics.getActualBoundingBox(match.index, match.index + match[0].length);
    return [match[0], box.x, box.right];
  });
  return words;
}

function drive(pane, scenario, dt) {
  const {scroll, hold, leave, live, ...actions} = scenario?.actions ?? {};
  return f => {
    const t = f * dt;
    if (f === scroll) pane.historyRows = pane.history(scenario.browseCaption, t);
    if (scroll <= f && f < live) return hold <= f && f < leave ? "holding" : "history";
    if (f === live) pane.historyRows = null;
    if (f === actions.hideOriginal) pane.sides[0] = false;
    if (f === actions.showOriginal) pane.sides[0] = true;
    if (f === actions.hideTranslation) pane.sides[1] = false;
    if (f === actions.showTranslation) pane.sides[1] = true;
    if (f === actions.switchMode) pane.mode = pane.mode === "instant" ? "scrolling" : "instant";
    pane.step(t);
    return "live";
  };
}

function capture(mode, source, settings, count, keyframes, scenario, makeInk, drive) {
  mcache.clear();
  params = settings;
  src = source;
  const pane = panes.find(p => p.mode === mode), e = pane.engine, g = () => e.g;
  e.reset(params, src);
  const advance = drive(e, scenario, DT);
  const ink = [], glyphKeys = new Map(), frames = [], shots = {};
  for (let frame = 0; frame <= count; frame++) {
    const t = frame * DT;
    const view = advance(frame);
    const rows = e.rows().map(row => {
      const {text, id, start, y, h, side, phase, scrolling} = row;
      const kind = side ? "translation" : "original";
      const glyphKey = kind + "|" + text;
      if (!glyphKeys.has(glyphKey)) {
        glyphKeys.set(glyphKey, ink.length);
        ink.push(makeInk(text, e.font(side), mctx));
      }
      const w = e.width(text.trimEnd(), side);
      const edge = g().pad + settings.origPx * 1.4;
      return {id, kind, index:start, start, text, x:g().pad-row.x, y, h, w, phase,
        scrolling, compact:scrolling, alpha:1, px:side ? settings.transPx : settings.origPx,
        inkIndex:glyphKeys.get(glyphKey), fadeWidth:row.x > 0.5 ? edge : 0,
        rightFadeWidth:w-row.x > g().avail + EPS ? edge : 0};
    });
    const admitted = [...new Set([...e.slots.values()]
      .filter(slot => slot.row.text && !slot.incoming).map(slot => slot.row.id))];
    frames.push({frame, rows, view, mode:e.mode, sides:e.sides.slice(), waiting:e.waiting, admitted});
    if (keyframes.includes(frame)) {
      drawPane(pane, t);
      const crop = document.createElement("canvas");
      crop.width = params.W;
      crop.height = params.H;
      crop.getContext("2d").drawImage(pane.canvas,36*pane.dpr,96*pane.dpr,
        params.W*pane.dpr,params.H*pane.dpr,0,0,params.W,params.H);
      shots[frame] = crop.toDataURL("image/png").split(",")[1];
    }
  }
  const events = e.events.map(({t, text}) => ({frame:Math.round(t * FPS), text}));
  return {frames, events, shots, glyphInk:ink, liveTop:g().foot-g().oLH-g().tLH-g().innerGap};
}

const probe = `
Promise.all([document.fonts.load('500 28px "Noto Sans"'), document.fonts.load('400 22px "Noto Sans SC"')]).then(loaded => {
  if (loaded.some(faces => faces.length !== 1)) throw Error("Missing reference font");
  const result = (${capture.toString()})(
    ${JSON.stringify(mode)}, ${JSON.stringify(source).replaceAll("<","\\u003c")},
    ${JSON.stringify(settings)}, ${lastFrame}, ${JSON.stringify(keyframes)},
    ${JSON.stringify(scenario)}, (${wordInk.toString()}), (${drive.toString()})
  );
  document.getElementById("caption-fonts").remove();
  document.body.replaceChildren(document.createElement("pre"));
  document.body.firstChild.textContent = JSON.stringify(result);
}).catch(error => { document.body.replaceChildren(document.createElement("pre"));
  document.body.firstChild.textContent = JSON.stringify({error: String(error)}); });
`;
const startup = page.lastIndexOf("\nsyncControls();");
assert(startup > page.indexOf("// ENGINE END"));
writeFileSync(html, '<meta charset="utf-8">' + page.slice(0, startup).replace(/<link\b[^>]*>/gi, "").replace("<style>", () => fontCss + "<style>") + probe + "</script>");
const chrome = process.env.CHROME_BIN || ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].find(existsSync);
if (!chrome) throw Error("Set CHROME_BIN to a Chromium executable");
function measureInBrowser() {
  try {
    const browser = spawnSync(chrome, [
      "--headless", "--enable-blink-features=ExtendedTextMetrics", "--disable-gpu", "--disable-background-networking",
      "--virtual-time-budget=15000", "--no-first-run", "--no-default-browser-check", "--force-device-scale-factor=1",
      "--user-data-dir=" + join(scratch, "profile"), "--dump-dom", pathToFileURL(html).href,
    ], {encoding: "utf8", windowsHide: true, maxBuffer: 32 * 1024 * 1024, timeout: 90000});
    if (browser.error) throw browser.error;
    const result = browser.stdout.match(/<pre>([\s\S]*?)<\/pre>/);
    if (browser.status !== 0 || !result) {
      throw Error("Headless browser did not return Canvas measurements");
    }
    return JSON.parse(result[1].replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&"));
  } finally {
    const target = realpathSync(scratch);
    if (dirname(target) !== realpathSync(out) || !target.startsWith(join(realpathSync(out),"browser-"))) {
      throw Error("Unexpected browser scratch path");
    }
    rmSync(target,{recursive:true,force:true,maxRetries:3});
  }
}
const captured = measureInBrowser();
if (captured.error) throw Error(captured.error);
const {shots, ...data} = captured;
for (const [frame, png] of Object.entries(shots)) {
  writeFileSync(join(out, "reference-" + frame + ".png"), Buffer.from(png,"base64"));
}
writeFileSync(join(out,"reference.json"),JSON.stringify({
  ...data, settings, scenario, size:[settings.W,settings.H], mode, fps:FPS, keyframes,
  source, translationLag:recorded ? 0 : LAT.transLive,
}));
console.log(`${preset} ${mode}: ${data.frames.length} frames, ${source.length} captions, ${data.events.length} events`);
