<p><img src="packaging/vicar-logo-long.png" alt="VICAR" height="56"></p>

# Sponge Lab by VICAR

Sponge Lab builds sponge ground truth from reef survey video. You watch a transect, click a sponge, and pick its species in a wheel. OpenCV follows the sponge through the video, and the app exports a table, frames, and crops. The Coverage grid shows, for each target species and video, what you tagged and how much of the video you watched.

![Sponge Lab playing a reef survey video, with species labels following tagged sponges, the video list on the left, and the species guide, sightings, and species tally on the right](docs/sponge-lab-demo.gif)

Sponge Lab keeps no videos. It streams them from an S3 bucket that you choose in project setup, with the TCRMP videos filled in.

## Install on a Mac

1. Download `SpongeLab-<version>.pkg` from [Releases](https://github.com/laurenkolinger/sponge-lab/releases/latest).
2. Double-click it. macOS blocks an installer from an unidentified developer the first time: open **System Settings > Privacy & Security**, click **Open Anyway**, and run it again.
3. Click through the installer. It needs no administrator password.
4. Sponge Lab opens and asks to download OpenCV and ffmpeg into its own folder, plus Python if you do not have version 3.14. This is up to about 400 MB. Click **Download** and stay connected to the internet. This changes nothing else on the computer.
5. Project setup appears. Click **Load videos** for the TCRMP videos, or enter another bucket and folder.

Tested on an Apple silicon Mac running macOS 27. Sponge Lab needs Google Chrome or another current browser. Windows is not supported yet.

If setup stops, open Sponge Lab again to retry. The reason is at the end of `~/Library/Logs/Sponge Lab by VICAR install.log`.

## Use another set of videos

Click **Project** at the top of the page and enter the bucket URL and folder. The bucket must allow public listing. Video file names must follow the TCRMP pattern, such as `TCRMP20241018_video_BIT_T1.MP4`, because the app reads the site and transect from them.

## Screening

- **Tag:** click a sponge, then pick a species in the wheel or press its number key.
- **Review:** press Space in the wheel to save a point without a species. The Review tab holds these points until you label them.
- **Hide marks:** click the eye button under the video to hide every mark and label on the picture, and click it again to bring them back. Hold Option to hide them only while you hold it. This works with the wheel open, so you can see a small sponge under its own mark before you pick its species.
- **Species colors:** Phase 1 is green, Phase 2 is pink, and Phase 3 is gray. Phases 1 and 2 are the eight target species, from Parts 1 and 2 of the ID guide.
- **Guide:** the guide opens beside the video in a window at least 1,100 pixels wide. Rest the pointer on a species name to see it there.
- **Coordinates:** `observations.csv` holds `PointX` and `PointY` for each click, as fractions of the frame from the top left. `tracks.csv` holds `X` and `Y` through time.

## Right panel

The panel beside the video has three tabs, and the app remembers the last one you used.

- **Video:** the sightings in the open video, with a line that counts its species, sightings, and points to review. Click a sighting to jump to it.
- **Review:** the points saved without a species, in every video. The count turns amber while any wait. Click one to open it in the wheel.
- **Diversity:** species richness and taxonomic coverage for all videos, one site, or the open video. It shows the species, sightings, genera, families, and orders; Shannon, Simpson, and Chao1; how much of the species list each rank and phase covers; species by site and by video; a species accumulation curve; and the species tally with its target.

Richness counts distinct species codes and leaves out Unknown sponge. A genus you added, such as *Cinachyrella*, counts as one taxon. Families and orders come from `config/taxonomy.csv`, taken from WoRMS; `tools/fetch_taxonomy.py` rebuilds it. The accumulation curve is the species you would expect after screening that many videos, averaged over every order of the videos (Mao Tau rarefaction). Screening targets some species, so the indices describe the sightings, not the reef.

## Coverage

The **Coverage** button opens a grid of the target species by every video in the folder on screen. J is the count from a reference file, and an amber cell means that file logged the species and nothing is tagged yet. A cell reads **none** only when every second was watched and nothing is left to review.

A stretch counts as watched while the video plays forward with the tab in view and no Coverage or shortcuts card open. Seeks, arrow-key scrubbing, and frame steps do not count, and a gap of 1 second or less counts as watched. The app cannot tell whether you were looking at the screen. A video finishes by itself once it is fully watched with nothing left to review.

To show reference counts, copy an earlier `observations.csv` to `reference_observations.csv` in the data folder. It needs the columns `Sponge Type` and `FileName`.

## Compare species and resize panes

Press C or click **Compare** in the guide for one photo of each species, side by side beside the video. Phases 1 and 2 show first, and the phase buttons add or hide a phase. Click a photo to enlarge it, or a name to see all of that species' photos. To choose which photo stands for a species, click the star on it in the species view. A species with no guide photo shows your first crop of it.

Drag the edge between any two panes to resize them, or focus the edge and use the arrow keys. Double-click an edge for the default size. The app remembers your sizes in this browser.

## Export

**Export** opens a list of the sites and videos with sightings, and below it the species, grouped by phase. Uncheck what you want left out, and the app remembers that in this browser. An unchecked species stays out of the tables, images, summaries, and videos, so you can send collaborators only the target species. The last row keeps the amber Review points off the videos when unchecked. You then download one zip with the tables, frames, crops, and each chosen video, in `videos_tracked/`, with every ID and species code drawn on its tracked position in the phase colors. Review points show in amber on the videos and stay out of the tables. Each export also holds `species_summary.csv`, `site_summary.csv`, and `video_summary.csv` with the counts and richness of what it holds. Rendering runs in the background for a few minutes per video while you keep working, and the browser downloads the zip when it finishes. A video whose sightings have not changed reuses its last render.

## Add a genus or species

Type the name in the wheel or the filter box. When nothing matches, press Enter, or click **Add** in the filter box, then confirm. A name with a hyphen or a period goes in the filter box, because the wheel does not take those keys. The name joins the list as Phase 3 with a code such as CINA, and stays in `custom_species.csv` in the data folder. Delete its row there to remove it.

## Species names

`config/species.csv` holds current names. When a name changes, keep the code and add the earlier name to `config/species_name_changes.csv`. A search for the old name still finds the species, and the guide shows a notice.

## Reference photos

The guide ships with descriptions and no photos, because the photos carry other people's copyright. To add photos, put them in `<data folder>/guide/<CODE>/` and list their file names in that species' `images` in `guide/guide.json`.

## Where things go

Everything lives in your account:

- App: `~/Applications/Sponge Lab by VICAR.app`
- Sightings, images, and settings: `~/Library/Application Support/Sponge Lab by VICAR/data/`
- Video cache, capped at 60 GB: `~/Library/Application Support/Sponge Lab by VICAR/cache/`
- Exports: click **Export**, choose the sites and videos, and the browser downloads one zip.

To stop the server:

```bash
launchctl kill SIGTERM gui/$(id -u)/org.vicar.sponge-lab.server
```

To uninstall, run the commands below and remove the Dock icon.

```bash
launchctl bootout gui/$(id -u)/org.vicar.sponge-lab.server
rm -rf ~/Applications/"Sponge Lab by VICAR.app" ~/Library/Application\ Support/"Sponge Lab by VICAR"
rm -f ~/Library/LaunchAgents/org.vicar.sponge-lab.server.plist ~/Library/Logs/"Sponge Lab by VICAR install.log"
pkgutil --volume ~ --forget org.vicar.sponge-lab
```

## Build from source

Python 3.14 runs the app with no packages. Tracking needs the packages in `requirements.txt`, in a virtual environment at `.venv-track`, and video conversion needs ffmpeg.

```bash
python3 screener.py
```

Tests:

```bash
python3 -m pytest tests -q
node --test tests/test_track_math.mjs tests/test_scrub.mjs tests/test_wheel.mjs tests/test_geometry.mjs tests/test_coverage.mjs tests/test_panes.mjs
```

The end-to-end tests need Chrome, ffmpeg, and node 20.10 or newer. Build the installer with:

```bash
packaging/build_pkg.sh
```
