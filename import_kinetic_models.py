import os
from pathlib import Path
import re
from typing import Any, Iterable, List, NamedTuple, Optional, Tuple, Union
from multiprocessing import Pool, cpu_count
from dateutil import parser


import habanero
import requests
from dotenv import load_dotenv
from github import Github
from github.ContentFile import ContentFile
from github.Repository import Repository

from models import KineticModel, Kinetics, Source, Author, Thermo, Transport, Species, Isomer, Structure, NamedSpecies

load_dotenv()

Seconds = Union[int, float]


class DownloadPath(NamedTuple):
    path: Path
    download_url: str


class ModelDir(NamedTuple):
    name: str
    thermo_path: Path
    kinetics_path: Path
    source_path: Path


class EnvironmentVariableMissing(Exception):
    pass


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


def download_rmg_models(data_path: Path = Path("rmg-models")) -> None:
    PAT = os.getenv("PAT")
    g = Github(PAT)
    owner_name = "kianmehrabani"
    repo_name = "RMG-models"
    repo = g.get_repo(f"{owner_name}/{repo_name}")
    contents: list[ContentFile] = repo.get_contents("")
    paths = get_paths(repo, data_path, contents)

    thread_pool = Pool(cpu_count())
    thread_pool.map(download, paths)


def get_model_paths(data_path: Path, ignore_list: List[str] = []) -> Iterable[ModelDir]:
    for path in data_path.iterdir():
        name = path.name
        thermo_path = path / "RMG-Py-thermo-library" / "ThermoLibrary.py"
        kinetics_path = path / "RMG-Py-kinetics-library" / "reactions.py"
        source_path = path / "source.txt"
        paths = [thermo_path, kinetics_path, source_path]

        if path.is_dir() and name not in ignore_list and all(p.exists() for p in paths):
            yield ModelDir(
                name=name,
                thermo_path=thermo_path,
                kinetics_path=kinetics_path,
                source_path=source_path
            )

def create_test_kinetic_model() -> KineticModel:
    structure = Structure(adjlist="", smiles="", multiplicity=0)
    isomer = Isomer(formula="", inchi="", structures=[structure])
    species = Species(isomers=[isomer])
    named_species = NamedSpecies(name="", species=species)
    author = Author(firstname="kian", lastname="mehrabani")
    source = Source(doi="", publication_year=0, title="", journal_name="", journal_volume="", page_numbers="", authors=[author])
    transport = Transport(species=species, geometry=0, well_depth=0, collision_diameter=0, dipole_moment=0, polarizability=0, rotational_relaxation=0, source=source)
    kinetic_model = KineticModel(name="", named_species=[named_species], transport=[transport], source=source)

    return kinetic_model


class MissingAuthorData(Exception):
    pass


class InvalidAuthorData(Exception):
    pass


# class AuthorEntry(Protocol):
#     given: Optional[str]
#     family: Optional[str]


class DOIError(Exception):
    pass


def create_authors(author_entries: Iterable[Any]) -> Iterable[Author]:
    for entry in author_entries:
        if entry.given is None or entry.family is None:
            raise InvalidAuthorData(entry)
        yield Author(firstname=entry.given, lastname=entry.family)


def get_doi(source_path: Path):
    """
    Get the DOI from the source.txt file
    """

    with open(source_path, "r") as f:
        source = f.read()

    regex = re.compile(r"10.\d{4,9}/\S+")
    matched_list = regex.findall(source)
    matched_list = [d.rstrip(".") for d in matched_list]
    # There are sometimes other trailing characters caught up, like ) or ]
    # We should probably clean up the source.txt files
    # But let's try cleaning them here.

    def clean(doi):
        for opening, closing in ["()", "[]"]:
            if doi.endswith(closing):
                if doi.count(closing) - doi.count(opening) == 1:
                    # 1 more closing than opening
                    # remove the last closing
                    doi = doi[:-1]
        return doi

    matched_list = [clean(d) for d in matched_list]
    matched_set = set(matched_list)

    if len(matched_set) == 0:
        raise DOIError(f"DOI not found for path: {source_path}")
    elif len(matched_set) > 1:
        raise DOIError(f"Found multiple DOIS: {matched_set}")
    else:
        return matched_list[0]


def create_source(path: Path) -> Source:
    crossref = habanero.Crossref(mailto="kianmehrabani@gmail.com")
    doi = get_doi(path)
    reference = crossref.works(ids=doi).get("message", "") if doi else {}
    created_info = reference.get("created", {})
    date = parser.parse(created_info.get("date-time", "")) if created_info else None
    year = date.year if date else ""
    title_body = reference.get("title", "")
    source_title = title_body[0] if isinstance(title_body, list) else title_body
    name_body = reference.get("short-container-title", "")
    journal_name = name_body[0] if isinstance(name_body, list) else name_body
    volume_number = reference.get("volume", "")
    page_numbers = reference.get("page", "")
    author_data = reference.get("author")

    if author_data is None:
        raise MissingAuthorData(path.name)

    authors = create_authors(author_data)

    return Source(
        doi=doi,
        publication_year=year,
        title=source_title,
        journal_name=journal_name,
        journal_volume=volume_number,
        page_numbers=page_numbers,
        authors=list(authors),
    )


def create_thermo(path: Path) -> Tuple[Iterable[Thermo], Iterable[NamedSpecies]]:
    ...


def create_kinetics(path: Path) -> Tuple[Iterable[Kinetics], Iterable[NamedSpecies]]:
    ...


def create_kinetic_model(model_dir: ModelDir) -> KineticModel:
    try:
        source = create_source(model_dir.source_path)
        thermo, named_species1 = create_thermo(model_dir.thermo_path)
        kinetics, named_species2 = create_kinetics(model_dir.kinetics_path)

        return KineticModel(
            name=model_dir.name,
            named_species=[*named_species1, *named_species2],
            thermo=thermo,
            kinetics=kinetics,
            source=source,
        ) # type: ignore

    catch 

def import_rmg_models(endpoint: str, data_path: Path = Path("rmg-models")) -> None:
    model_dirs = get_model_paths(data_path)
    for model_dir in model_dirs:
        km = create_kinetic_model(model_dir)
        response = requests.post(endpoint, data=km.json(exclude_none=True, exclude_unset=True))


if __name__ == "__main__":
    endpoint = os.getenv("POST_ENDPOINT")
    if endpoint is None:
        raise EnvironmentVariableMissing("POST_ENDPOINT not set")
    import_rmg_models(endpoint)
