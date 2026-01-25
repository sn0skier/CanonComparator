# CanComp (canoncomparator)

CanComp compares your library’s track counts per MusicBrainz release-group (RGID) against the most common (“mode”) track count among releases in that release-group on MusicBrainz.

It supports:
- Lidarr as a library provider
- MusicBrainz lookups with caching (SQLite)
- Manual canon overrides per release-group

## Install (recommended)

### Install as User

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
# restart your terminal (or: source ~/.bashrc)
pipx install git+https://github.com/sn0skier/CanonComparator.git
```

Test with `canoncomparator --help`
> If `canoncomparator` is “command not found”, run `pipx ensurepath` and restart your terminal.

### Install as Developer

```bash
git clone <your-repo-url>
cd CanonComparator
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Configure

Create:

`~/.config/cancomp/config.toml`

Example:

```toml
[lidarr]
url = "[your lidarr webui url, usually http://localhost:8686]"
api_key = "[Your Lidarr API Key]"

[paths]
cache = "~/.cache/cancomp/mb_cache.sqlite"

[musicbrainz]
app_name = "CanonComparator"
version = "0.1.2"
contact = "https://github.com/sn0skier/CanonComparator" # REPLACE WITH A WAY TO CONTACT ***YOU*** if you fork or branch this project!!!
cache_max_age_days = 365 # -1 to never refetch, 0 to always refetch
```

## Optional overrides:

Optionally, if you want to be able to manually override the canon track count definitions for specific albums, create:

`~/.config/cancomp/overrides.toml`

Example:

```toml
# Override the mode(TrackCounts) definition of canon with manual values or leave blank to allow any value
# Make sure to save before running script. You can optionally alphabetize this list when running CanonComparator 
# If the script overwrites this file you will lose any #commented notes that you have entered here
# Format "{MBReleaseGroupID}" = [{TrackCount(optional)}, ...] #{ReleaseGroupName}
[canon]
# "ExampleMBReleaseGroupID" = [10, 15] #(optional: Example Artist - Example Release Group Name)
```

## Run

Run with:

`canoncomparator`

First run can take quite a while depending on library size as it will need to build the local cache of the MusicBrainz Database. MB's rules state that you can only make an API call once per second, so keep that in mind.

By default it writes cancomp_<timestamp>.csv in the current directory; use --out to choose a path/name.

`canoncomparator --out [desired directory]/[desired filename].csv`

For testing:

`canoncomparator --limit-albums 25 --limit-rgids 5 --out ./test.csv`

To sort overrides (overwrites the `overrides.toml` file):

`canoncomparator --sort-overrides`

## CSV columns explained

Each row represents a single MusicBrainz release-group (RGID) present in your library.

| Column | Meaning |
|------|--------|
| `rgid` | MusicBrainz Release Group ID |
| `mb_release_group_url` | Direct link to the MusicBrainz release-group web page |
| `artist` | Artist name as reported by the library provider (Lidarr) |
| `title` | Release-group title as reported by the library provider (Lidarr) |
| `owned_track_count` | Total number of tracks you own for this release-group (all discs summed) |
| `canon_track_counts` | Track counts considered “canon” (from overrides or MB mode: see `mb_mode_track_count`) |
| `min_owned_minus_canon` | If any canon count matches owned, this is 0. Otherwise it is the closest signed difference between owned and canon counts (negative means you own fewer tracks than the nearest canon value; positive means more). Blank if canon counts are unavailable. |
| `owned_matches_canon` | `True` if your library's track count matches any canon value (`min_owned_minus_canon` = 0). Blank if canon counts are unavailable (e.g., MB fetch failed and no override exists). |
| `canon_source` | Where canon values came from (`override`, `mb_mode`, or `none`) |
| `mb_mode_track_count` | Most common track count among MB releases in this release-group |
| `diff_owned_minus_mode` | Your library's track count minus MB mode track count |
| `mode_release_count` | Number of MB releases that have the mode track count |
| `owned_trackcount_release_count` | Number of MB releases that match your library's track count |
| `mb_release_count` | Total number of MB releases in the release-group |
| `mb_histogram_tracks_releases_json` | JSON mapping `"TrackCount": ReleaseCount` |
| `mb_fetch_status` | How MB data was obtained for this RGID (cached, fetched (not in cache), fetched (cache expired), or failed (...)). If it’s failed, MB-derived fields may be blank. |
| `override_suggestion` | Ready-to-copy entry for `overrides.toml` |

---