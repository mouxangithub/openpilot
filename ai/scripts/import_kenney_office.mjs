#!/usr/bin/env node
/**
 * Import curated Kenney CC0 models from _staging into vendor/office/.
 * Usage: node ai/scripts/import_kenney_office.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STAGING = path.join(__dirname, '../web/static/vendor/office/_staging');
const OUT = path.join(__dirname, '../web/static/vendor/office');
const TEXTURES_OUT = path.join(OUT, 'textures');

const PICKS = [
  // furniture — office interior
  { src: 'furniture/Models/GLTF format/desk.glb', dest: 'desk.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/chairDesk.glb', dest: 'chair.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/computerScreen.glb', dest: 'monitor.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/loungeSofa.glb', dest: 'sofa.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/plantSmall1.glb', dest: 'plant.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/tableCoffee.glb', dest: 'coffee-table.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/kitchenCoffeeMachine.glb', dest: 'coffee-machine.glb', kit: 'furniture' },
  { src: 'furniture/Models/GLTF format/bookcaseClosed.glb', dest: 'bookcase.glb', kit: 'furniture' },
  // roads — lane / engage / crossroad
  { src: 'roads/Models/GLB format/road-straight.glb', dest: 'road-straight.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/road-bend.glb', dest: 'road-bend.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/road-crossroad-line.glb', dest: 'road-crossroad.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/road-crossroad-path.glb', dest: 'road-crossroad-path.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/construction-barrier.glb', dest: 'barrier.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/construction-cone.glb', dest: 'cone.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/light-square.glb', dest: 'street-light.glb', kit: 'roads' },
  { src: 'roads/Models/GLB format/road-end.glb', dest: 'road-end.glb', kit: 'roads' },
  // racing — replay track + vehicle + flags
  { src: 'racing/Models/GLTF format/roadStraight.glb', dest: 'track-straight.glb', kit: 'racing' },
  { src: 'racing/Models/GLTF format/roadCornerSmall.glb', dest: 'track-corner.glb', kit: 'racing' },
  { src: 'racing/Models/GLTF format/roadStart.glb', dest: 'track-start.glb', kit: 'racing' },
  { src: 'racing/Models/GLTF format/raceCarRed.glb', dest: 'vehicle-sedan.glb', kit: 'racing' },
  { src: 'racing/Models/GLTF format/barrierRed.glb', dest: 'race-barrier.glb', kit: 'racing' },
  { src: 'racing/Models/GLTF format/flagCheckers.glb', dest: 'flag-checkers.glb', kit: 'racing' },
  { src: 'racing/Models/GLTF format/lightRed.glb', dest: 'traffic-light.glb', kit: 'racing' },
];

const CHARACTER_PICKS = [
  { src: 'characters/Models/GLB format/character-male-a.glb', dest: 'character-male-a.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-male-b.glb', dest: 'character-male-b.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-male-c.glb', dest: 'character-male-c.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-male-d.glb', dest: 'character-male-d.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-male-e.glb', dest: 'character-male-e.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-male-f.glb', dest: 'character-male-f.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-female-a.glb', dest: 'character-female-a.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-female-b.glb', dest: 'character-female-b.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-female-c.glb', dest: 'character-female-c.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-female-d.glb', dest: 'character-female-d.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-female-e.glb', dest: 'character-female-e.glb', kit: 'characters' },
  { src: 'characters/Models/GLB format/character-female-f.glb', dest: 'character-female-f.glb', kit: 'characters' },
];

const TEXTURE_GLOBS = [
  'furniture/Models/GLTF format/Textures/colormap.png',
  'roads/Models/GLB format/Textures/colormap.png',
  'racing/Models/GLTF format/Textures/colormap.png',
  'characters/Models/GLB format/Textures/colormap.png',
];

function findFile(rel) {
  const full = path.join(STAGING, rel);
  if (fs.existsSync(full)) return full;
  // fuzzy: match basename anywhere under kit folder
  const kit = rel.split('/')[0];
  const base = path.basename(rel);
  const root = path.join(STAGING, kit);
  if (!fs.existsSync(root)) return null;
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) stack.push(p);
      else if (ent.name === base) return p;
    }
  }
  return null;
}

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function main() {
  if (!fs.existsSync(STAGING)) {
    console.error(`Staging missing: ${STAGING}`);
    console.error('Extract zips to vendor/office/_staging/{furniture,roads,racing} first.');
    process.exit(1);
  }

  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(TEXTURES_OUT, { recursive: true });

  let ok = 0;
  const missing = [];
  const allPicks = [...PICKS, ...CHARACTER_PICKS];
  for (const pick of allPicks) {
    const src = findFile(pick.src);
    const dest = path.join(OUT, pick.dest);
    if (!src) {
      missing.push(pick.src);
      continue;
    }
    copyFile(src, dest);
    const stat = fs.statSync(dest);
    console.log(`✓ ${pick.dest} <- ${path.relative(STAGING, src)} (${stat.size} B)`);
    ok += 1;
  }

  for (const rel of TEXTURE_GLOBS) {
    const src = findFile(rel);
    if (!src) continue;
    const kit = rel.split('/')[0];
    const destName = `${kit}-colormap.png`;
    copyFile(src, path.join(TEXTURES_OUT, destName));
    console.log(`✓ textures/${destName}`);
  }

  // Kenney license copies
  for (const kit of ['furniture', 'roads', 'racing', 'characters']) {
    const lic = findFile(`${kit}/License.txt`);
    if (lic) copyFile(lic, path.join(OUT, `LICENSE-${kit}.txt`));
  }

  console.log(`\nImported ${ok}/${allPicks.length} models → ${OUT}`);
  if (missing.length) {
    console.warn('\nMissing (check filenames in zip):');
    missing.forEach((m) => console.warn(`  - ${m}`));
  }
}

main();
