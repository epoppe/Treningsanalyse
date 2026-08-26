#!/usr/bin/env node
/**
 * Build desktop/assets/icon.ico from icon.png (run from desktop/).
 */
const fs = require("fs");
const path = require("path");

async function main() {
  const pngToIco = require("png-to-ico").default;
  const assets = path.join(__dirname, "..", "assets");
  const png = path.join(assets, "icon.png");
  if (!fs.existsSync(png)) {
    console.error("Missing", png);
    process.exit(1);
  }
  const buf = await pngToIco(png);
  fs.writeFileSync(path.join(assets, "icon.ico"), buf);
  console.log("Wrote", path.join(assets, "icon.ico"));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
