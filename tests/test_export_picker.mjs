/** Tests for the choices of the Export picker. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(path.join(here, '..', 'static', 'export_picker.js'), 'utf8');
const {
  exportLabel, exportRequest, groupByPhase, groupBySite, groupState, phaseOfSpecies, setGroup, speciesCounts, videoCounts,
} = await import(
  `data:text/javascript;base64,${Buffer.from(source, 'utf8').toString('base64')}`
);

const VIDEOS = [
  { key: 'a', site: 'Buck Island', transect: 'T1', sightings: 35, review: 7 },
  { key: 'b', site: 'Buck Island', transect: 'T2', sightings: 1, review: 0 },
  { key: 'c', site: 'Flat Cay', transect: 'T1', sightings: 8, review: 0 },
];

test('groupBySite keeps the order and handles no videos', () => {
  assert.deepEqual(groupBySite(VIDEOS).map((group) => [group.site, group.videos.length]), [['Buck Island', 2], ['Flat Cay', 1]]);
  assert.deepEqual(groupBySite([]), []);
});

test('groupState reads all, some, and none', () => {
  assert.equal(groupState(VIDEOS, new Set()), 'all');
  assert.equal(groupState(VIDEOS, new Set(['a'])), 'some');
  assert.equal(groupState(VIDEOS, new Set(['a', 'b', 'c'])), 'none');
});

test('setGroup leaves out and restores one site without touching the other', () => {
  const site = groupBySite(VIDEOS)[1].videos;
  const out = setGroup(site, new Set(['a']), false);
  assert.deepEqual([...out].sort(), ['a', 'c']);
  assert.deepEqual([...setGroup(site, out, true)], ['a']);
});

test('exportRequest names keys only for part of the videos', () => {
  assert.deepEqual(exportRequest(VIDEOS, new Set()), {});
  assert.deepEqual(exportRequest(VIDEOS, new Set(['c'])), { keys: ['a', 'b'] });
});

test('exportRequest ignores a remembered key that no longer has sightings', () => {
  assert.deepEqual(exportRequest(VIDEOS, new Set(['gone'])), {});
});

test('exportLabel and videoCounts count correctly', () => {
  assert.equal(exportLabel(VIDEOS, new Set(['a'])), 'Export 2 videos');
  assert.equal(exportLabel(VIDEOS, new Set(['a', 'b'])), 'Export 1 video');
  assert.equal(videoCounts(VIDEOS[0]), '35 sightings, 7 review');
  assert.equal(videoCounts(VIDEOS[1]), '1 sighting');
});

const SPECIES = [
  { key: 'ACAU', code: 'ACAU', part: '1', sightings: 93, videos: 8 },
  { key: 'ACOM', code: 'ACOM', part: '2', sightings: 64, videos: 7 },
  { key: 'PANG', code: 'PANG', part: '3', sightings: 28, videos: 5 },
  { key: 'CINA', code: 'CINA', part: '', sightings: 4, videos: 1 },
  { key: 'UNKN', code: 'UNKN', part: '', sightings: 1, videos: 1 },
];

test('phaseOfSpecies puts custom species in Phase 3 and UNKN in none', () => {
  assert.equal(phaseOfSpecies('1', 'ACAU'), '1');
  assert.equal(phaseOfSpecies('2', 'ACOM'), '2');
  assert.equal(phaseOfSpecies('3', 'PANG'), '3');
  assert.equal(phaseOfSpecies('', 'CINA'), '3');
  assert.equal(phaseOfSpecies('', 'UNKN'), '');
  assert.equal(phaseOfSpecies(undefined, 'XXXX'), '3');
});

test('groupByPhase keeps phase order and drops empty phases', () => {
  const groups = groupByPhase(SPECIES);
  assert.deepEqual(groups.map((group) => [group.label, group.species.map((item) => item.code)]), [
    ['Phase 1', ['ACAU']],
    ['Phase 2', ['ACOM']],
    ['Phase 3', ['PANG', 'CINA']],
    ['Other', ['UNKN']],
  ]);
  assert.deepEqual(groupByPhase([SPECIES[2]]).map((group) => group.label), ['Phase 3']);
  assert.deepEqual(groupByPhase([]), []);
});

test('exportRequest names codes only for part of the species', () => {
  assert.deepEqual(exportRequest(VIDEOS, new Set(), SPECIES, new Set()), {});
  assert.deepEqual(exportRequest(VIDEOS, new Set(), SPECIES, new Set(['PANG', 'CINA', 'UNKN'])), { codes: ['ACAU', 'ACOM'] });
  assert.deepEqual(
    exportRequest(VIDEOS, new Set(['c']), SPECIES, new Set(['UNKN'])),
    { keys: ['a', 'b'], codes: ['ACAU', 'ACOM', 'PANG', 'CINA'] },
  );
});

test('exportRequest ignores a remembered code that no longer has sightings', () => {
  assert.deepEqual(exportRequest(VIDEOS, new Set(), SPECIES, new Set(['GONE'])), {});
});

test('exportRequest sends review only when the Review points stay out', () => {
  assert.deepEqual(exportRequest(VIDEOS, new Set(), SPECIES, new Set(), true), {});
  assert.deepEqual(exportRequest(VIDEOS, new Set(), SPECIES, new Set(), false), { review: false });
});

test('exportLabel names the species only when some are left out', () => {
  assert.equal(exportLabel(VIDEOS, new Set(), SPECIES, new Set()), 'Export 3 videos');
  assert.equal(exportLabel(VIDEOS, new Set(['a']), SPECIES, new Set(['PANG', 'CINA', 'UNKN'])), 'Export 2 videos, 2 species');
  assert.equal(exportLabel(VIDEOS, new Set(), SPECIES, new Set(['ACAU', 'ACOM', 'PANG', 'CINA', 'UNKN'])), 'Export 3 videos, 0 species');
});

test('speciesCounts words one and many videos', () => {
  assert.equal(speciesCounts(SPECIES[0]), '93 in 8 videos');
  assert.equal(speciesCounts(SPECIES[3]), '4 in 1 video');
});
