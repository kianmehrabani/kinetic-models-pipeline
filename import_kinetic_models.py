import os
from pathlib import Path
from typing import Iterable

import requests
from github import Github
from github.ContentFile import ContentFile

def download_rmg_models():
    def get_paths(contents: list[ContentFile]) -> Iterable[tuple[Path, str]]:
        for content in contents:
            if content.type == "dir":
                yield from get_paths(repo.get_contents(content.path))
            else:
                yield (data_path / content.path, content.download_url)

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
        content = requests.get(url).content
        path.write_bytes(content)
