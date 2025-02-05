#!/usr/bin/env python3

import argparse
import csv
import os
from pathlib import Path
import requests
import shutil
import tempfile
import sys


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="Download the input GTFS feeds",
    )
    parser.add_argument("--output", required=True, help="output directory")

    assert not sys.stdin.isatty(), "expecting a filtered MobilityDatabase CSV on stdin"
    args = parser.parse_args()

    eprint("args", args)

    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        for row in csv.DictReader(sys.stdin):
            feed_id = "headway-" + row["mdb_source_id"]

            if row["data_type"] != "gtfs":
                eprint("Skipping row", feed_id, "because it's not a gtfs feed")
                continue

            unzipped_name = feed_id + ".gtfs"
            unzipped_path = tmpdir + "/" + unzipped_name
            zipfile_path = tmpdir + "/" + unzipped_name + ".zip"

            with open(zipfile_path, "wb") as f:
                eprint("Downloading feed for", row["provider"], "to", zipfile_path)
                response = requests.get(row["urls.latest"])
                f.write(response.content)

            eprint("Unzipping", zipfile_path, "to", unzipped_path)
            shutil.unpack_archive(zipfile_path, unzipped_path)

            eprint("Rewriting agency ID to ensure it's unique across feeds")
            feed_info_fieldnames = None
            feed_info_row = None
            with open(unzipped_path + "/feed_info.txt", "r") as feed_info_file:
                feed_info_reader = csv.DictReader(feed_info_file)
                feed_info_fieldnames = feed_info_reader.fieldnames

                for feed_info in feed_info_reader:
                    if feed_info_row is not None:
                        # OTP uses the feed_id as an identifier for joining
                        # GTFS-RT feeds.
                        #
                        # AFAIK there are no references within the GTFS file
                        # to this key, so we shouldn't break any consistency by
                        # changing it.
                        #
                        # One thing that's weird is that for aggregate feeds,
                        # it's customary to specify multiple entries in feed_info.txt
                        # Since none of the internal entities within the GTFS
                        # archive reference any of these id's, theres no way to
                        # distinguish which feed an individual entity came
                        # from. And thus, OTP must consider all the feeds as
                        # essentially the same.
                        #
                        # It looks like OTP just grabs the first one:
                        #
                        # https://github.com/opentripplanner/OpenTripPlanner/blob/c9f713c639b48164825471c499ce67f58ebeb15b/src/main/java/org/opentripplanner/graph_builder/module/GtfsFeedId.java#L68
                        #
                        # In any case, I'm going to ignore all but the first entry
                        # to simplify this concern.
                        eprint("ignoring subsequent rows in feed_info.txt")
                    feed_info_row = feed_info
                    feed_info_row["feed_id"] = feed_id

            assert (
                feed_info_row is not None
            ), "expected at least one row in feed_info.text"

            # Replace existing csv
            with open(unzipped_path + "/feed_info.txt", "w") as feed_info_file:
                if not "feed_id" in feed_info_fieldnames:
                    # Some feeds don't have a feed_id (e.g. Whatcom County Transit)
                    feed_info_fieldnames.insert(0, "feed_id")
                csv_writer = csv.DictWriter(
                    feed_info_file, fieldnames=feed_info_fieldnames
                )
                csv_writer.writeheader()
                csv_writer.writerow(feed_info_row)

            output_path = output_dir + "/" + feed_id + ".gtfs"
            eprint("writing modified zip to", output_path + ".zip")
            shutil.make_archive(output_path, "zip", unzipped_path)


if __name__ == "__main__":
    main()
