/**
 * The pure parts of the Diversity tab: which summary a scope shows, how its numbers read, the
 * taxonomic coverage rows, the taxonomy tree, and the geometry of its small charts. This file
 * holds no page state and imports nothing, so the node tests run it without a browser.
 *
 * The numbers come from GET /api/diversity (screener/diversity.py). This file never computes
 * an index itself, so the page and the export always agree.
 */

/** The scopes the tab can show. */
export const SCOPES = Object.freeze(['all', 'site', 'video']);

/** The ranks of the taxonomic coverage rows, in order, with the key each summary uses. */
export const RANKS = Object.freeze([
  { rank: 'species', label: 'Species' },
  { rank: 'genus', label: 'Genera' },
  { rank: 'family', label: 'Families' },
  { rank: 'order', label: 'Orders' },
]);

/** The phases of the ID guide, with the tier name the stylesheet colors them by. */
const PHASE_ROWS = Object.freeze([
  { part: '1', tier: 'original', label: 'Phase 1' },
  { part: '2', tier: 'added', label: 'Phase 2' },
  { part: '3', tier: 'other', label: 'Phase 3' },
]);

/** The name of the group for taxa that config/taxonomy.csv does not classify. */
const UNCLASSIFIED = 'Unclassified';

/** What a missing number reads as. */
const MISSING = '–';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** The tick steps a chart axis may use, times a power of ten. */
const TICK_STEPS = [1, 2, 5, 10];

/** The most ticks an axis shows, beyond the 0 tick. */
const MAX_TICKS = 5;

/**
 * Write a YYYY-MM-DD date as a day, a short month, and a year.
 * @param {string} iso The date, or "" when the video name holds none.
 * @returns {string} Such as 18 Oct 2024, or "" for an empty or impossible date.
 */
export function formatDate(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso ?? ''));
  if (!match) {
    return '';
  }
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return '';
  }
  return `${day} ${MONTHS[month - 1]} ${match[1]}`;
}

/**
 * Name one video for a heading: its site and transect, then its date.
 * @param {{name: string, site: string, transect: string, date: string}} video A video summary.
 * @returns {string} Such as Buck Island T1, 18 Oct 2024; the file name when the name is
 *   outside the TCRMP pattern.
 */
export function videoTitle(video) {
  const place = [video.site, video.transect].filter(Boolean).join(' ');
  if (!place) {
    return video.name;
  }
  const day = formatDate(video.date);
  return day ? `${place}, ${day}` : place;
}

/**
 * Pick the summary a scope shows.
 * @param {?object} payload The answer of GET /api/diversity, or null before it loads.
 * @param {string} scope "all", "site", or "video".
 * @param {string} site The site chosen for the site scope, or "".
 * @param {string} videoKey The key of the open video, or "".
 * @returns {{summary: ?object, title: string, empty: string}} The summary, a heading, and,
 *   when there is no summary, the sentence the tab shows instead.
 * @throws {TypeError} When scope is not one of SCOPES.
 */
export function pickScope(payload, scope, site, videoKey) {
  if (!SCOPES.includes(scope)) {
    throw new TypeError(`pickScope: scope must be all, site, or video, got ${JSON.stringify(scope)}`);
  }
  if (!payload) {
    return { summary: null, title: '', empty: 'The numbers are loading.' };
  }
  if (scope === 'all') {
    return { summary: payload.all, title: 'All videos', empty: '' };
  }
  if (scope === 'site') {
    if (!site) {
      return { summary: null, title: '', empty: 'Pick a site to see its numbers.' };
    }
    const found = payload.sites.find((item) => item.site === site) || null;
    return { summary: found, title: site, empty: found ? '' : 'No sightings at this site yet.' };
  }
  if (!videoKey) {
    return { summary: null, title: '', empty: 'Open a video to see its numbers.' };
  }
  const found = payload.videos.find((item) => item.key === videoKey) || null;
  return {
    summary: found,
    title: found ? videoTitle(found) : '',
    empty: found ? '' : 'No sightings in this video yet.',
  };
}

/**
 * Write a number for a tile or a table.
 * @param {?number} value The number, or null when it is undefined for this scope.
 * @param {number} decimals How many decimals to show.
 * @returns {string} The number, or a dash when it is missing.
 */
export function formatNumber(value, decimals) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  return value.toFixed(decimals);
}

/**
 * Join a count and its noun.
 * @param {number} count The count.
 * @param {string} one The noun for one.
 * @param {string} [many] The noun for any other count; one plus "s" when left out.
 * @returns {string} Such as 1 video or 2 genera.
 */
export function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

/**
 * Work out the share of a reference that a count reaches, held between 0 and 1.
 * @param {number} seen The observed count.
 * @param {number} total The reference count.
 * @returns {number} seen / total, or 0 when the reference is 0.
 */
function shareOf(seen, total) {
  if (!(total > 0)) {
    return 0;
  }
  return Math.min(1, Math.max(0, seen / total));
}

/**
 * Lay out the taxonomic coverage rows of a summary: how much of the reference list it holds
 * at each rank and in each phase.
 * @param {{reference: object, phases: Array<{part: string, total: number}>}} payload The answer
 *   of GET /api/diversity.
 * @param {object} summary The summary of the scope on screen.
 * @returns {{ranks: Array<object>, phases: Array<object>}} Each row holds its label, seen,
 *   total, and share; a phase row holds its tier too.
 */
export function coverageRows(payload, summary) {
  const ranks = RANKS.map(({ rank, label }) => {
    const seen = Number(summary[rank]) || 0;
    const total = Number(payload.reference[rank]) || 0;
    return { label, seen, total, share: shareOf(seen, total) };
  });
  const totals = new Map(payload.phases.map((item) => [String(item.part), Number(item.total) || 0]));
  const phases = PHASE_ROWS.map(({ part, tier, label }) => {
    const seen = Number(summary.phases?.[part]) || 0;
    const total = totals.get(part) || 0;
    return { label, tier, seen, total, share: shareOf(seen, total) };
  });
  return { ranks, phases };
}

/**
 * Sort group names alphabetically with the unclassified group last.
 * @param {string} a One name.
 * @param {string} b The other name.
 * @returns {number} The comparison.
 */
function byNameUnclassifiedLast(a, b) {
  if ((a === UNCLASSIFIED) !== (b === UNCLASSIFIED)) {
    return a === UNCLASSIFIED ? 1 : -1;
  }
  return a.localeCompare(b);
}

/**
 * Nest the reference taxa by order and family, with the sightings of each in a scope.
 * @param {Array<{code: string, name: string, family: string, order: string}>} taxa The
 *   reference list from GET /api/diversity.
 * @param {Object<string, number>} counts Labeled sightings per code in the scope.
 * @returns {Array<{name: string, seen: number, total: number, families: Array<object>}>} One
 *   entry per order, by name, with taxa the taxonomy does not classify last. A family holds
 *   its name, seen, total, and species ({code, name, count}) by name.
 */
export function taxonomyTree(taxa, counts) {
  const orders = new Map();
  for (const taxon of taxa) {
    const orderName = taxon.order || UNCLASSIFIED;
    const familyName = taxon.family || UNCLASSIFIED;
    if (!orders.has(orderName)) {
      orders.set(orderName, new Map());
    }
    const families = orders.get(orderName);
    if (!families.has(familyName)) {
      families.set(familyName, []);
    }
    families.get(familyName).push({ code: taxon.code, name: taxon.name, count: Number(counts?.[taxon.code]) || 0 });
  }
  const seenIn = (species) => species.filter((item) => item.count > 0).length;
  return [...orders.keys()].sort(byNameUnclassifiedLast).map((orderName) => {
    const families = [...orders.get(orderName).keys()].sort(byNameUnclassifiedLast).map((familyName) => {
      const species = orders.get(orderName).get(familyName).slice().sort((a, b) => a.name.localeCompare(b.name));
      return { name: familyName, seen: seenIn(species), total: species.length, species };
    });
    return {
      name: orderName,
      seen: families.reduce((sum, family) => sum + family.seen, 0),
      total: families.reduce((sum, family) => sum + family.total, 0),
      families,
    };
  });
}

/**
 * Scale a list of values for a bar chart, keeping the order given.
 * @param {Array<*>} items The items.
 * @param {function(*): string} labelOf Names an item.
 * @param {function(*): number} valueOf Measures an item.
 * @returns {Array<{item: *, label: string, value: number, share: number}>} One row per item;
 *   share is the value over the largest value, or 0 when every value is 0.
 */
export function barRows(items, labelOf, valueOf) {
  const values = items.map((item) => Math.max(0, Number(valueOf(item)) || 0));
  const max = Math.max(0, ...values);
  return items.map((item, index) => ({
    item,
    label: labelOf(item),
    value: values[index],
    share: max > 0 ? values[index] / max : 0,
  }));
}

/**
 * Choose the ticks of an axis that starts at 0: a step of 1, 2, or 5 times a power of ten,
 * with at most MAX_TICKS steps, ending at or past the maximum.
 * @param {number} max The largest value on the axis.
 * @returns {Array<number>} The ticks, from 0.
 */
export function niceTicks(max) {
  const top = Math.max(1, Number(max) || 0);
  const magnitude = 10 ** Math.floor(Math.log10(top));
  let step = magnitude;
  for (const multiple of TICK_STEPS) {
    step = multiple * magnitude;
    if (Math.ceil(top / step) <= MAX_TICKS) {
      break;
    }
  }
  const step1 = Math.max(1, step);
  const ticks = [];
  for (let value = 0; value < top + step1; value += step1) {
    ticks.push(value);
    if (value >= top) {
      break;
    }
  }
  return ticks;
}

/**
 * Lay out the species accumulation curve in a chart of a given size. The curve starts at the
 * origin (no videos, no species) and runs through each point.
 * @param {Array<{videos: number, species: number}>} points The expected richness after m videos.
 * @param {{width: number, height: number, left: number, right: number, top: number,
 *   bottom: number}} size The chart and its margins, in pixels.
 * @returns {?{path: string, dots: Array<object>, xTicks: Array<object>, yTicks: Array<object>,
 *   plot: {x0: number, y0: number, x1: number, y1: number}}} The line, one dot per point (with
 *   its videos and species), the ticks with their positions, and the plot area; null without points.
 * @throws {TypeError} When the margins leave no room for a plot.
 */
export function accumulationGeometry(points, size) {
  const x0 = size.left;
  const x1 = size.width - size.right;
  const y0 = size.height - size.bottom;
  const y1 = size.top;
  if (!(x1 - x0 > 0) || !(y0 - y1 > 0)) {
    throw new TypeError(`accumulationGeometry: size leaves no room for a plot, got ${JSON.stringify(size)}`);
  }
  if (!points.length) {
    return null;
  }
  const lastVideos = points[points.length - 1].videos;
  const yValues = niceTicks(Math.max(...points.map((point) => point.species)));
  const yTop = yValues[yValues.length - 1];
  const xAt = (videos) => x0 + (videos / Math.max(1, lastVideos)) * (x1 - x0);
  const yAt = (species) => y0 - (species / yTop) * (y0 - y1);
  const dots = points.map((point) => ({ x: xAt(point.videos), y: yAt(point.species), videos: point.videos, species: point.species }));
  const path = [`M${x0.toFixed(1)} ${y0.toFixed(1)}`, ...dots.map((dot) => `L${dot.x.toFixed(1)} ${dot.y.toFixed(1)}`)].join(' ');
  // The last tick is always the number of videos; a regular tick within half a
  // step gives way, so their labels never collide.
  const xValues = niceTicks(lastVideos).filter((value) => value <= lastVideos);
  const xStep = xValues.length > 1 ? xValues[1] - xValues[0] : 1;
  if (xValues[xValues.length - 1] !== lastVideos) {
    if (xValues.length > 1 && lastVideos - xValues[xValues.length - 1] <= xStep / 2) {
      xValues.pop();
    }
    xValues.push(lastVideos);
  }
  return {
    path,
    dots,
    xTicks: xValues.map((value) => ({ x: xAt(value), value })),
    yTicks: yValues.map((value) => ({ y: yAt(value), value })),
    plot: { x0, y0, x1, y1 },
  };
}
