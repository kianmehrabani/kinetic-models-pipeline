import os
from pathlib import Path
from typing import Iterable, List, NamedTuple

import requests
from github import Github
from github.ContentFile import ContentFile


class DownloadPath(NamedTuple):
    path: Path
    download_url: str


def download_rmg_models():
    def get_paths(contents: List[ContentFile]) -> Iterable[DownloadPath]:
        for content in contents:
            if content.type == "dir":
                yield from get_paths(repo.get_contents(content.path))
            else:
                yield DownloadPath(data_path / content.path, content.download_url)

    TIMEOUT = 10  # seconds
    PAT = os.environ.get("PAT")
    g = Github(PAT)
    owner_name = "kianmehrabani"
    repo_name = "RMG-models"
    repo = g.get_repo(f"{owner_name}/{repo_name}")
    contents: list[ContentFile] = repo.get_contents("")
    data_path = Path("rmg-models")
    paths = get_paths(contents)

    for path, url in paths:
        path.parent.mkdir(exist_ok=True, parents=True)
        content = requests.get(url, timeout=TIMEOUT).content
        path.write_bytes(content)
