/* Copy the static site into dist/. No bundler: the page is three files plus
 * the pipeline's JSON, and keeping it dependency-free means the deploy cannot
 * break on a toolchain upgrade. */
import { cp, mkdir, rm, stat, readdir } from 'node:fs/promises';
import { join } from 'node:path';

const OUT = 'dist';
await rm(OUT, { recursive: true, force: true });
await mkdir(OUT, { recursive: true });

for (const f of ['index.html', 'app.js', 'styles.css']) {
  await cp(f, join(OUT, f));
}
await cp('public', OUT, { recursive: true });

async function size(dir) {
  let total = 0;
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    total += e.isDirectory() ? await size(p) : (await stat(p)).size;
  }
  return total;
}
const dataDir = join(OUT, 'data');
try {
  const n = (await readdir(dataDir)).length;
  console.log(`built ${OUT}/  (${n} data files, ${(await size(OUT) / 1e6).toFixed(1)} MB)`);
} catch {
  console.warn(`built ${OUT}/ but public/data is empty — run "make mock" first`);
}
