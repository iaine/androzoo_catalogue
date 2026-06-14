'''
Backend processing for the AndroZoo catalogue.

This module is pure logic: it knows how to build a shell pipeline that
searches the AndroZoo `latest.csv.gz` list, run it, save the result as a
CSV, and (optionally) download APKs by sha256. It has no UI knowledge so
it can be driven by pywebview, Flask, or the command line.

Expected AndroZoo `latest.csv` columns (1-indexed for awk):
    $1 sha256   $2 sha1     $3 md5        $4 dex_date   $5 apk_size
    $6 pkg_name $7 vercode  $8 vt_detection $9 vt_scan_date
    $10 dex_date $11 markets
The `markets` field separates multiple stores with `|`, so `-F,` is safe.
'''
from datetime import datetime
import os
import re
import shlex
import subprocess

import requests

# Path to the gzipped catalogue. Override with the AZ_CATALOGUE env var.
CATALOGUE = os.environ.get("AZ_CATALOGUE", "../../historical/latest.csv.gz")
# AndroZoo API key for downloads. Override with the AZ_APIKEY env var.
API_KEY = os.environ.get("AZ_APIKEY", "")
# Where result CSVs and downloaded APKs are written.
RESULTS_DIR = os.environ.get("AZ_RESULTS_DIR", "results")
EXTRACT_DIR = os.environ.get("AZ_EXTRACT_DIR", "extract")


class AndroZoo:

    def __init__(self, catalogue=CATALOGUE, api_key=API_KEY,
                 results_dir=RESULTS_DIR, extract_dir=EXTRACT_DIR):
        self.catalogue = catalogue
        self.api_key = api_key
        self.results_dir = results_dir
        self.extract_dir = extract_dir
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.extract_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def _clean_regex(self, value):
        '''
        Turn a user-supplied package/store fragment into a safe awk regex.

        - A leading/trailing `*` is treated as a wildcard (anchor relaxed).
        - Absence of `*` anchors that side of the match.
        - All other regex metacharacters are escaped so the user gets a
          literal substring match rather than accidental regex behaviour.
        '''
        value = value.strip()

        anchor_start = not value.startswith('*')
        anchor_end = not value.endswith('*')
        core = value.strip('*')

        # Escape every regex metacharacter (incl. '.') for a literal match.
        core = re.escape(core)

        if anchor_start:
            core = '^' + core
        if anchor_end:
            core = core + '$'
        return core

    def build_command(self, apk_name="", store="", start="", end=""):
        '''
        Build a shell pipeline that filters the catalogue.

        Filters are additive: any combination of name/store/start/end may
        be supplied and all supplied conditions must match. Raises
        ValueError if no filter is given (refusing to dump the whole list).
        '''
        cat = shlex.quote(self.catalogue)
        # `|| true` on grep: exit code 1 just means "no lines matched the
        # exclusion", which is not an error. zcat failures still propagate
        # via pipefail.
        cmd = ("set -o pipefail; /usr/bin/zcat < " + cat +
               " | { grep -v ',snaggamea' || true; } ")

        conditions = []
        if apk_name.strip():
            conditions.append('$6 ~ /{}/'.format(self._clean_regex(apk_name)))
        if store.strip():
            conditions.append('$11 ~ /{}/'.format(self._clean_regex(store)))
        if start.strip():
            conditions.append('$4 >= "{}"'.format(start.strip()))
        if end.strip():
            conditions.append('$4 <= "{}"'.format(end.strip()))

        if not conditions:
            raise ValueError("Provide at least one search filter.")

        cmd += "| awk -F, '{{if ({}) {{print}}}}'".format(" && ".join(conditions))
        return cmd

    def store_name(self, apk=""):
        '''Build a timestamped output filename for a search result.'''
        nowtime = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r'[^A-Za-z0-9._-]', '_', apk) or "search"
        return os.path.join(self.results_dir, "{}_{}.csv".format(nowtime, safe))

    def get_data(self, command, apk=""):
        '''
        Run the search pipeline and write matching rows to a CSV file.

        Returns the path to the result file. The file is removed if the
        pipeline fails so a stale/empty file is never left behind.
        '''
        fname = self.store_name(apk=apk)
        try:
            with open(fname, "w") as fh:
                subprocess.run(
                    command, shell=True, stdout=fh,
                    stderr=subprocess.PIPE, text=True, check=True,
                    executable="/bin/bash",
                )
            return fname
        except subprocess.CalledProcessError as e:
            if os.path.exists(fname):
                os.remove(fname)
            raise RuntimeError(
                "Search failed (exit {}): {}".format(e.returncode, e.stderr)
            ) from e

    def search(self, apk_name="", store="", start="", end=""):
        '''Convenience: build the command, run it, return result info.'''
        command = self.build_command(apk_name, store, start, end)
        label = apk_name or store or "search"
        path = self.get_data(command, apk=label)
        with open(path) as fh:
            count = sum(1 for _ in fh)
        return {"path": os.path.abspath(path), "matches": count}

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #
    def get_shas(self, result_csv):
        '''Extract the sha256 column (field 1) from a result CSV.'''
        result = subprocess.run(
            ["cut", "-d,", "-f1", result_csv],
            capture_output=True, text=True, check=True,
        )
        return [s for s in result.stdout.splitlines() if s.strip()]

    def process_apk(self, sha):
        '''Download a single APK by sha256 into the extract directory.'''
        saved_apk = os.path.join(self.extract_dir, sha + ".apk")
        apk_url = "https://androzoo.uni.lu/api/download?apikey={}&sha256={}".format(
            self.api_key, sha
        )
        try:
            resp = requests.get(apk_url, timeout=120)
            resp.raise_for_status()
            with open(saved_apk, "wb") as out:
                out.write(resp.content)
            return saved_apk
        except Exception as e:  # noqa: BLE001 - log and continue on batch jobs
            print("Failed to download {}: {}".format(sha, e))
            return None

    def collect_apks(self, shalist):
        '''Download a list of APKs concurrently.'''
        from multiprocessing.pool import ThreadPool
        if not self.api_key:
            raise ValueError("AZ_APIKEY is not set; cannot download APKs.")
        with ThreadPool(5) as pool:
            return pool.map(self.process_apk, shalist)

    def download(self, result_csv):
        '''Download every APK referenced in a result CSV.'''
        return self.collect_apks(self.get_shas(result_csv))


# ---------------------------------------------------------------------- #
# Command-line entry point
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Search the AndroZoo catalogue.")
    parser.add_argument("-n", "--name", default="", help="package name fragment")
    parser.add_argument("-s", "--store", default="", help="market/store fragment")
    parser.add_argument("--start", default="", help="earliest dex_date (YYYY-MM-DD)")
    parser.add_argument("--end", default="", help="latest dex_date (YYYY-MM-DD)")
    parser.add_argument("--download", action="store_true",
                        help="download matching APKs after searching")
    args = parser.parse_args()

    az = AndroZoo()
    info = az.search(args.name, args.store, args.start, args.end)
    print("{matches} matches written to {path}".format(**info))
    if args.download:
        print("Downloading APKs...")
        az.download(info["path"])
