#!/usr/bin/env python3
"""Convert a Jazzy MCAP bag's metadata for ROS 2 Humble playback."""

import argparse
import shutil
import subprocess
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag_dir", type=Path)
    args = parser.parse_args()

    bag_dir = args.bag_dir.resolve()
    metadata = bag_dir / "metadata.yaml"
    backup = bag_dir / "metadata.jazzy.yaml"
    if not metadata.is_file():
        parser.error(f"missing {metadata}")
    if not backup.exists():
        shutil.copy2(metadata, backup)

    subprocess.run(["ros2", "bag", "reindex", "-s", "mcap", str(bag_dir)], check=True)
    data = yaml.safe_load(metadata.read_text())
    topics = data["rosbag2_bagfile_information"]["topics_with_message_count"]
    for topic in topics:
        # Humble cannot parse the QoS YAML emitted by Jazzy. The demo topics
        # use reliable publishers, which match Humble's default playback QoS.
        topic["topic_metadata"]["offered_qos_profiles"] = ""
    metadata.write_text(yaml.safe_dump(data, sort_keys=False))


if __name__ == "__main__":
    main()
