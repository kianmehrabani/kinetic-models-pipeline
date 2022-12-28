import os
from pathlib import Path
from typing import Iterable, List, NamedTuple, Type, Union
from multiprocessing import Pool, cpu_count

import requests
from dotenv import load_dotenv
from github import Github
from github.ContentFile import ContentFile
from github.Repository import Repository


Seconds = Union[int, float]


class DownloadPath(NamedTuple):
    path: Path
    download_url: str


def get_paths(repo: Repository, data_path: Path, contents: List[ContentFile]) -> Iterable[DownloadPath]:
    for content in contents:
        if content.type == "dir":
            yield from get_paths(repo, data_path, repo.get_contents(content.path))
        else:
            yield DownloadPath(data_path / content.path, content.download_url)


def download(download_path: DownloadPath, timeout: Seconds = 10) -> None:
    path, url = download_path
    path.parent.mkdir(exist_ok=True, parents=True)
    content = requests.get(url, timeout=timeout).content
    path.write_bytes(content)


def download_rmg_models():
    load_dotenv()
    PAT = os.getenv("PAT")
    g = Github(PAT)
    owner_name = "kianmehrabani"
    repo_name = "RMG-models"
    repo = g.get_repo(f"{owner_name}/{repo_name}")
    contents: list[ContentFile] = repo.get_contents("")
    data_path = Path("rmg-models")
    paths = get_paths(repo, data_path, contents)

    thread_pool = Pool(cpu_count())
    thread_pool.map(download, paths)
