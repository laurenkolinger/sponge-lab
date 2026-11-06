/**
 * The choices of the Export picker. This file holds no page state, so the node tests can run
 * it without a browser.
 */

/**
 * Group the videos on offer by site, keeping their order.
 * @param {Array<{key: string, site: string}>} videos The videos with sightings.
 * @returns {Array<{site: string, videos: Array<object>}>} One entry per site.
 */
export function groupBySite(videos) {
  const groups = new Map();
  for (const video of videos) {
    if (!groups.has(video.site)) {
      groups.set(video.site, []);
    }
    groups.get(video.site).push(video);
  }
  return [...groups].map(([site, members]) => ({ site, videos: members }));
}

/**
 * Say how much of a group is checked.
 * @param {Array<{key: string}>} videos The group.
 * @param {Set<string>} unchecked The keys left out.
 * @returns {'all'|'some'|'none'} The state of the group's checkbox.
 */
export function groupState(videos, unchecked) {
  const left = videos.filter((video) => unchecked.has(video.key)).length;
  if (left === 0) {
    return 'all';
  }
  return left === videos.length ? 'none' : 'some';
}

/**
 * Check or uncheck a whole group.
 * @param {Array<{key: string}>} videos The group.
 * @param {Set<string>} unchecked The keys left out.
 * @param {boolean} checked True checks the group.
 * @returns {Set<string>} The new keys left out.
 */
export function setGroup(videos, unchecked, checked) {
  const next = new Set(unchecked);
  for (const video of videos) {
    if (checked) {
      next.delete(video.key);
    } else {
      next.add(video.key);
    }
  }
  return next;
}

/** The phases of the ID guide, in picker order. Custom species and Part 3 are Phase 3. */
export const PHASE_GROUPS = Object.freeze([
  { phase: '1', tier: 'original', label: 'Phase 1' },
  { phase: '2', tier: 'added', label: 'Phase 2' },
  { phase: '3', tier: 'other', label: 'Phase 3' },
  { phase: '', tier: 'other', label: 'Other' },
]);

/**
 * Name the phase group of a species from its ID guide part.
 * @param {string} part The guide part: "1", "2", "3", or "" for a custom species or UNKN.
 * @param {string} code The species code. UNKN (Unknown sponge) has no phase.
 * @returns {string} "1", "2", "3", or "" for UNKN.
 */
export function phaseOfSpecies(part, code) {
  const text = String(part ?? '');
  if (text === '1' || text === '2') {
    return text;
  }
  return code === 'UNKN' ? '' : '3';
}

/**
 * Group the species on offer by phase, keeping their order and dropping empty phases.
 * @param {Array<{key: string, code: string, part: string}>} species The species with sightings.
 * @returns {Array<{phase: string, tier: string, label: string, species: Array<object>}>} One entry
 *   per phase that has species.
 */
export function groupByPhase(species) {
  return PHASE_GROUPS
    .map((group) => ({ ...group, species: species.filter((item) => phaseOfSpecies(item.part, item.code) === group.phase) }))
    .filter((group) => group.species.length > 0);
}

/**
 * Build the request for the checked videos and species. Every video checked sends no list,
 * so the export covers whatever has sightings when it starts; every species checked sends no
 * codes for the same reason; the Review points are sent only when they are left out.
 * @param {Array<{key: string}>} videos The videos on offer.
 * @param {Set<string>} unchecked The video keys left out.
 * @param {Array<{key: string}>} [species] The species on offer, keyed by code.
 * @param {Set<string>} [uncheckedSpecies] The codes left out.
 * @param {boolean} [review] False keeps the Review points off the drawn videos.
 * @returns {{keys?: Array<string>, codes?: Array<string>, review?: boolean}} The body of the request.
 */
export function exportRequest(videos, unchecked, species = [], uncheckedSpecies = new Set(), review = true) {
  const body = {};
  const keys = videos.filter((video) => !unchecked.has(video.key)).map((video) => video.key);
  if (keys.length !== videos.length) {
    body.keys = keys;
  }
  const codes = species.filter((item) => !uncheckedSpecies.has(item.key)).map((item) => item.key);
  if (codes.length !== species.length) {
    body.codes = codes;
  }
  if (review === false) {
    body.review = false;
  }
  return body;
}

/**
 * Name the picker's button.
 * @param {Array<{key: string}>} videos The videos on offer.
 * @param {Set<string>} unchecked The video keys left out.
 * @param {Array<{key: string}>} [species] The species on offer, keyed by code.
 * @param {Set<string>} [uncheckedSpecies] The codes left out.
 * @returns {string} The label, such as Export 6 videos, or Export 6 videos, 8 species when
 *   some species are left out.
 */
export function exportLabel(videos, unchecked, species = [], uncheckedSpecies = new Set()) {
  const count = videos.filter((video) => !unchecked.has(video.key)).length;
  const label = `Export ${count} video${count === 1 ? '' : 's'}`;
  const chosen = species.filter((item) => !uncheckedSpecies.has(item.key)).length;
  if (chosen === species.length) {
    return label;
  }
  return `${label}, ${chosen} species`;
}

/**
 * Word one video's counts.
 * @param {{sightings: number, review: number}} video The video.
 * @returns {string} The counts, such as 35 sightings, 7 review.
 */
export function videoCounts(video) {
  const sightings = `${video.sightings} sighting${video.sightings === 1 ? '' : 's'}`;
  return video.review ? `${sightings}, ${video.review} review` : sightings;
}

/**
 * Word one species' counts.
 * @param {{sightings: number, videos: number}} species The species.
 * @returns {string} The counts, such as 35 in 4 videos.
 */
export function speciesCounts(species) {
  return `${species.sightings} in ${species.videos} video${species.videos === 1 ? '' : 's'}`;
}
