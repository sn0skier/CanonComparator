# CanComp (canoncomparator)

CanComp compares your library’s track counts per MusicBrainz release-group (RGID) against the most common (“mode”) track count among releases in that release-group on MusicBrainz.

It supports:
- Lidarr as a library provider
- MusicBrainz lookups with caching (SQLite)
- Manual canon overrides per release-group

## Install (recommended)

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
version = "0.1.0"
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

---