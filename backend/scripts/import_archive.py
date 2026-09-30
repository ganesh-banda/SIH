"""Copy CSV and metadata members from the supplied archive into data/raw."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from app.config import get_settings


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("archive",type=Path)
    args=parser.parse_args()
    raw=get_settings().raw_dir
    raw.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.archive) as archive:
        for info in archive.infolist():
            if info.is_dir(): continue
            name=Path(info.filename).name
            if not name or Path(info.filename).parts[0]!="synthetic_btc_dataset":
                raise ValueError(f"Unexpected archive member: {info.filename}")
            if Path(info.filename).suffix.lower() not in (".csv",".json",".md",".txt",".py"):
                raise ValueError(f"Unexpected archive member: {info.filename}")
            destination=raw/name
            if destination.exists() and destination.read_bytes()!=archive.read(info):
                raise FileExistsError(f"Different raw file exists: {destination}")
            destination.write_bytes(archive.read(info))
            print(destination)


if __name__=="__main__": main()
