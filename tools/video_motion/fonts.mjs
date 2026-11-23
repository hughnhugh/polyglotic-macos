import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const revision = "06bfe0d62a98375cb09c942fa18e68bd32cff057";
const fonts = [
  ["Noto Sans", "NotoSans.ttf", "notosans/NotoSans%5Bwdth,wght%5D.ttf",
    "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d"],
  ["Noto Sans SC", "NotoSansSC.ttf", "notosanssc/NotoSansSC%5Bwght%5D.ttf",
    "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da"],
];

export async function captionFontCss() {
  const cache = resolve(process.env.VIDEO_REFERENCE_FONTS || "build/video-motion-fonts");
  mkdirSync(cache, { recursive: true });
  const rules = [];
  for (const [family, file, path, hash] of fonts) {
    const target = join(cache, file);
    let bytes;
    if (existsSync(target)) {
      bytes = readFileSync(target);
    } else {
      const url = "https://raw.githubusercontent.com/google/fonts/" + revision + "/ofl/" + path;
      const response = await fetch(url);
      if (!response.ok) throw Error("Font download failed: " + response.status + " " + url);
      bytes = Buffer.from(await response.arrayBuffer());
    }
    if (createHash("sha256").update(bytes).digest("hex") !== hash) {
      throw Error("Unexpected font checksum: " + target);
    }
    if (!existsSync(target)) {
      const temporary = target + "." + randomUUID();
      try {
        writeFileSync(temporary, bytes);
        renameSync(temporary, target);
      } finally {
        rmSync(temporary, { force: true });
      }
    }
    rules.push(`@font-face{font-family:"${family}";font-weight:100 900;src:url(data:font/ttf;base64,${bytes.toString("base64")})}`);
  }
  return '<style id="caption-fonts">' + rules.join("\n") + "</style>";
}
