/** Tests for the pure parts of the Diversity tab. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(path.join(here, '..', 'static', 'diversity_view.js'), 'utf8');
const {
  accumulationGeometry, barRows, coverageRows, formatDate, formatNumber, niceTicks, pickScope, plural, taxonomyTree,
} = await import(`data:text/javascript;base64,${Buffer.from(source, 'utf8').toString('base64')}`);

const SUMMARY = (extra = {}) => ({
  videos: 2, sites: 1, sightings: 10, review: 1, unknown: 0, species: 3, genus: 2, family: 2, order: 1,
  phases: { 1: 1, 2: 1, 3: 1 }, shannon: 1.0, simpson: 0.6, chao1: 3.5,
  counts: { ACAU: 6, AFUL: 3, PANG: 1 }, video_counts: { ACAU: 2, AFUL: 1, PANG: 1 },
  accumulation: [{ videos: 1, species: 2.5 }, { videos: 2, species: 3 }],
  ...extra,
});

const PAYLOAD = {
  reference: { species: 4, genus: 3, family: 3, order: 2 },
  phases: [{ part: '1', total: 1 }, { part: '2', total: 1 }, { part: '3', total: 2 }],
  taxa: [
    { code: 'ACAU', name: 'Aplysina cauliformis', part: '1', genus: 'Aplysina', family: 'Aplysinidae', order: 'Verongiida', class: 'Demospongiae' },
    { code: 'AFUL', name: 'Aplysina fulva', part: '2', genus: 'Aplysina', family: 'Aplysinidae', order: 'Verongiida', class: 'Demospongiae' },
    { code: 'PANG', name: 'Plakortis angulospiculatus', part: '3', genus: 'Plakortis', family: 'Plakinidae', order: 'Homosclerophorida', class: 'Homoscleromorpha' },
    { code: 'XNEW', name: 'Xenia newgenus', part: '', genus: 'Xenia', family: '', order: '', class: '' },
  ],
  all: SUMMARY(),
  sites: [{ site: 'Buck Island', ...SUMMARY() }],
  videos: [
    { key: 'k1', name: 'TCRMP20241018_video_BIT_T1.MP4', site: 'Buck Island', transect: 'T1', date: '2024-10-18', status: 'in progress', ...SUMMARY({ videos: 1 }) },
  ],
};

test('pickScope answers all, a site, and a video', () => {
  assert.equal(pickScope(PAYLOAD, 'all', '', '').summary, PAYLOAD.all);
  assert.equal(pickScope(PAYLOAD, 'all', '', '').title, 'All videos');
  assert.equal(pickScope(PAYLOAD, 'site', 'Buck Island', '').summary, PAYLOAD.sites[0]);
  assert.equal(pickScope(PAYLOAD, 'video', '', 'k1').summary, PAYLOAD.videos[0]);
  assert.equal(pickScope(PAYLOAD, 'video', '', 'k1').title, 'Buck Island T1, 18 Oct 2024');
  const odd = { ...PAYLOAD, videos: [{ ...PAYLOAD.videos[0], site: '', transect: '', date: '', name: 'odd.mov' }] };
  assert.equal(pickScope(odd, 'video', '', 'k1').title, 'odd.mov');
});

test('pickScope explains an empty scope instead of failing', () => {
  assert.equal(pickScope(PAYLOAD, 'site', '', '').summary, null);
  assert.match(pickScope(PAYLOAD, 'site', '', '').empty, /site/);
  assert.equal(pickScope(PAYLOAD, 'site', 'Flat Cay', '').summary, null);
  assert.match(pickScope(PAYLOAD, 'video', '', '').empty, /Open a video/);
  assert.match(pickScope(PAYLOAD, 'video', '', 'missing').empty, /No sightings/);
  assert.equal(pickScope(null, 'all', '', '').summary, null);
  assert.throws(() => pickScope(PAYLOAD, 'reef', '', ''), /scope/);
});

test('formatNumber shows a dash for a missing value and rounds the rest', () => {
  assert.equal(formatNumber(null, 2), '–');
  assert.equal(formatNumber(undefined, 2), '–');
  assert.equal(formatNumber(Number.NaN, 2), '–');
  assert.equal(formatNumber(2.4567, 2), '2.46');
  assert.equal(formatNumber(12, 0), '12');
  assert.equal(formatNumber(0, 1), '0.0');
});

test('formatDate writes a day, a short month, and a year', () => {
  assert.equal(formatDate('2024-10-18'), '18 Oct 2024');
  assert.equal(formatDate('2024-01-05'), '5 Jan 2024');
  assert.equal(formatDate(''), '');
  assert.equal(formatDate('2024-13-01'), '');
});

test('plural picks the word by count', () => {
  assert.equal(plural(1, 'video'), '1 video');
  assert.equal(plural(0, 'video'), '0 videos');
  assert.equal(plural(2, 'genus', 'genera'), '2 genera');
});

test('coverageRows divides observed by reference at each rank and phase', () => {
  const rows = coverageRows(PAYLOAD, PAYLOAD.all);
  assert.deepEqual(rows.ranks.map((row) => [row.label, row.seen, row.total]), [
    ['Species', 3, 4], ['Genera', 2, 3], ['Families', 2, 3], ['Orders', 1, 2],
  ]);
  assert.equal(rows.ranks[0].share, 0.75);
  assert.deepEqual(rows.phases.map((row) => [row.label, row.tier, row.seen, row.total]), [
    ['Phase 1', 'original', 1, 1], ['Phase 2', 'added', 1, 1], ['Phase 3', 'other', 1, 2],
  ]);
});

test('coverageRows keeps a share inside 0 to 1 when a reference is 0 or smaller', () => {
  const payload = { ...PAYLOAD, reference: { species: 0, genus: 1, family: 1, order: 1 } };
  const rows = coverageRows(payload, SUMMARY({ genus: 5 }));
  assert.equal(rows.ranks[0].share, 0);
  assert.equal(rows.ranks[1].share, 1);
});

test('taxonomyTree nests order, family, and species, unclassified last', () => {
  const tree = taxonomyTree(PAYLOAD.taxa, { ACAU: 6, PANG: 1 });
  assert.deepEqual(tree.map((order) => [order.name, order.seen, order.total]), [
    ['Homosclerophorida', 1, 1], ['Verongiida', 1, 2], ['Unclassified', 0, 1],
  ]);
  const verongiida = tree[1];
  assert.deepEqual(verongiida.families.map((family) => [family.name, family.seen, family.total]), [['Aplysinidae', 1, 2]]);
  assert.deepEqual(verongiida.families[0].species.map((item) => [item.code, item.count]), [['ACAU', 6], ['AFUL', 0]]);
  assert.deepEqual(taxonomyTree([], {}), []);
});

test('barRows scales to the largest value and survives all zeros', () => {
  const rows = barRows([{ n: 'a', v: 4 }, { n: 'b', v: 2 }], (item) => item.n, (item) => item.v);
  assert.deepEqual(rows.map((row) => [row.label, row.value, row.share]), [['a', 4, 1], ['b', 2, 0.5]]);
  assert.deepEqual(barRows([{ n: 'a', v: 0 }], (item) => item.n, (item) => item.v)[0].share, 0);
  assert.deepEqual(barRows([], (item) => item, (item) => item), []);
});

test('niceTicks steps by 1, 2, 5, or 10 and covers the maximum', () => {
  assert.deepEqual(niceTicks(0), [0, 1]);
  assert.deepEqual(niceTicks(3), [0, 1, 2, 3]);
  assert.deepEqual(niceTicks(7), [0, 2, 4, 6, 8]);
  assert.deepEqual(niceTicks(28), [0, 10, 20, 30]);
  assert.deepEqual(niceTicks(41), [0, 10, 20, 30, 40, 50]);
});

test('accumulationGeometry starts at the origin and ends at the last point', () => {
  const size = { width: 200, height: 100, left: 20, right: 10, top: 10, bottom: 20 };
  const geometry = accumulationGeometry([{ videos: 1, species: 2.5 }, { videos: 2, species: 3 }], size);
  assert.match(geometry.path, /^M20(\.0+)? 80(\.0+)? L/);
  const last = geometry.dots.at(-1);
  assert.equal(last.x, 190);
  assert.equal(last.videos, 2);
  assert.equal(last.species, 3);
  assert.ok(last.y >= 10 && last.y <= 80);
  assert.deepEqual(geometry.yTicks.map((tick) => tick.value), [0, 1, 2, 3]);
  assert.equal(geometry.xTicks.at(-1).value, 2);
});

test('accumulationGeometry answers null with no points and rejects a bad size', () => {
  const size = { width: 200, height: 100, left: 20, right: 10, top: 10, bottom: 20 };
  assert.equal(accumulationGeometry([], size), null);
  assert.throws(() => accumulationGeometry([{ videos: 1, species: 1 }], { ...size, width: 10 }), /size/);
});

test('accumulationGeometry drops a tick that would crowd the last one', () => {
  const size = { width: 260, height: 150, left: 28, right: 10, top: 8, bottom: 22 };
  const nine = Array.from({ length: 9 }, (_, index) => ({ videos: index + 1, species: index + 1 }));
  assert.deepEqual(accumulationGeometry(nine, size).xTicks.map((tick) => tick.value), [0, 2, 4, 6, 9]);
  const seven = nine.slice(0, 7);
  assert.deepEqual(accumulationGeometry(seven, size).xTicks.map((tick) => tick.value), [0, 2, 4, 7]);
  const eight = nine.slice(0, 8);
  assert.deepEqual(accumulationGeometry(eight, size).xTicks.map((tick) => tick.value), [0, 2, 4, 6, 8]);
  assert.deepEqual(accumulationGeometry([{ videos: 1, species: 3 }], size).xTicks.map((tick) => tick.value), [0, 1]);
});
