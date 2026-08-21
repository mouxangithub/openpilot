#!/usr/bin/env node
/**
 * Download optional CC0 office GLB assets into ai/web/static/vendor/office/
 *
 * Run on a dev machine (needs network), then commit the files:
 *   node ai/scripts/fetch_office_assets.mjs
 *
 * The 3D office works fully offline with procedural geometry (car, desks,
 * lane markings, Panda, steering wheel, etc.). GLB is optional polish only.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, '../web/static/vendor/office');

/**
 * Khronos sample URLs moved/404 on jsdelivr. Prefer manual Kenney CC0 zips:
 * - https://kenney.nl/assets/furniture-kit  → desk.glb, chair.glb, plant.glb, sofa.glb
 * - https://kenney.nl/assets/car-kit        → optional car.glb
 *
 * Place extracted GLBs in ai/web/static/vendor/office/ and update manifest.json.
 */
const ASSETS = [
  {
    name: 'chair.glb',
    urls: [
      'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/Chair/glTF-Binary/Chair.glb',
    ],
  },
  {
    name: 'plant.glb',
    urls: [
      'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/PottedPlant/glTF-Binary/PottedPlant.glb',
    ],
  },
];

async function fetchOne(url) {
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return Buffer.from(await res.arrayBuffer());
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  let ok = 0;
  for (const asset of ASSETS) {
    const dest = path.join(OUT, asset.name);
    if (fs.existsSync(dest) && fs.statSync(dest).size > 1000) {
      console.log(`skip ${asset.name} (exists)`);
      ok += 1;
      continue;
    }
    let saved = false;
    for (const url of asset.urls) {
      try {
        console.log(`fetch ${asset.name} <- ${url}`);
        const buf = await fetchOne(url);
        fs.writeFileSync(dest, buf);
        console.log(`  wrote ${buf.length} bytes`);
        ok += 1;
        saved = true;
        break;
      } catch (e) {
        console.warn(`  failed: ${e.message}`);
      }
    }
    if (!saved) console.warn(`! could not fetch ${asset.name} — use Kenney CC0 manual drop`);
  }
  console.log(`\nDone: ${ok}/${ASSETS.length} models in ${OUT}`);
  console.log('Procedural office theme does not require GLB. Optional: Kenney furniture-kit (CC0).');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
