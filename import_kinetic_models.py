import os
from pathlib import Path
import re
from typing import Any, Iterable, List, NamedTuple, Optional, Tuple, Union
from dateutil import parser


import habanero
import requests
from pydantic import ValidationError
from dotenv import load_dotenv
from rmgpy import kinetics, constants
from rmgpy.data.kinetics.library import KineticsLibrary
from rmgpy.data.thermo import ThermoLibrary
from rmgpy.thermo import NASA, ThermoData, Wilhoit, NASAPolynomial

from models import Arrhenius, ArrheniusEP, KineticModel, Kinetics, Reaction, Source, Author, Thermo, Transport, Species, Isomer, Structure, NamedSpecies

load_dotenv()

Seconds = Union[int, float]


class ModelDir(NamedTuple):
    name: str
    thermo_path: Path
    kinetics_path: Path
    source_path: Path


class EnvironmentVariableMissing(Exception):
    pass


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
    if author_entries is None:
        raise MissingAuthorData()
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


def create_source(path: Path) -> Optional[Source]:
    try:
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
    except (InvalidAuthorData, DOIError, ValidationError) as e:
        return None


def create_species(molecule) -> Species:
    formula = molecule.get_formula()
    inchi = molecule.to_augmented_inchi()
    smiles = molecule.to_smiles()
    adjacency_list = molecule.to_adjacency_list()
    multiplicity = molecule.multiplicity

    structure = Structure(smiles=smiles, adjacency_list=adjacency_list, multiplicity=multiplicity)
    isomer = Isomer(formula=formula, inchi=inchi, structures=[structure])

    return Species(isomers=[isomer])


def create_named_species(name: str, molecule) -> NamedSpecies:
    return NamedSpecies(name, create_species(molecule))


def create_thermo(path: Path) -> Iterable[Tuple[Thermo, NamedSpecies]]:
    local_context = {
        "ThermoData": ThermoData,
        "Wilhoit": Wilhoit,
        "NASAPolynomial": NASAPolynomial,
        "NASA": NASA,
    }
    library = ThermoLibrary(label=path)
    library.SKIP_DUPLICATES = True
    library.load(path, local_context=local_context)
    for species_name, entry in library.entries.items():
        species = create_named_species(species_name, entry.item)
        thermo_data = entry.data
        poly1, poly2 = thermo_data.polynomials
        thermo = Thermo(
            species=species,
            polynomial1=poly1.coeffs.tolist(),
            polynomial2=poly2.coeffs.tolist(),
            temp_min_1=poly1.Tmin.value_si,
            temp_max_1=poly1.Tmax.value_si,
            temp_min_2=poly2.Tmin.value_si,
            temp_max_2=poly2.Tmax.value_si,
        )

        yield thermo, species


def create_reaction(rmg_reaction) -> Reaction:
    ...

def create_kinetics_data(rmg_kinetics_data) -> Union[Arrhenius, ArrheniusEP]:
    ...

def create_kinetics(path: Path) -> Iterable[Kinetics]:
    local_context = {
        "KineticsData": kinetics.KineticsData,
        "Arrhenius": kinetics.Arrhenius,
        "ArrheniusEP": kinetics.ArrheniusEP,
        "MultiArrhenius": kinetics.MultiArrhenius,
        "MultiPDepArrhenius": kinetics.MultiPDepArrhenius,
        "PDepArrhenius": kinetics.PDepArrhenius,
        "Chebyshev": kinetics.Chebyshev,
        "ThirdBody": kinetics.ThirdBody,
        "Lindemann": kinetics.Lindemann,
        "Troe": kinetics.Troe,
        "R": constants.R,
    }
    library = KineticsLibrary(label=path)
    library.SKIP_DUPLICATES = True
    library.load(path, local_context=local_context)
    for entry in library.entries.values():
        rmg_kinetics_data = entry.data
        rmg_reaction = entry.item
        reaction = create_reaction(rmg_reaction)
        kinetics_data = create_kinetics_data(rmg_kinetics_data)

        min_temp = getattr(rmg_kinetics_data.Tmin, "value_si", None)
        max_temp = getattr(rmg_kinetics_data.Tmax, "value_si", None)
        min_pressure = getattr(rmg_kinetics_data.Pmin, "value_si", None)
        max_pressure = getattr(rmg_kinetics_data.Pmax, "value_si", None)

        yield Kinetics(
            reaction=reaction,
            data=kinetics_data,
            source=None,
            for_reverse=False,
            min_temp=min_temp,
            max_temp=max_temp,
            min_pressure=min_pressure,
            max_pressure=max_pressure,
        )

def create_kinetic_model(model_dir: ModelDir) -> KineticModel:
    source = create_source(model_dir.source_path)
    thermo, named_species = create_thermo(model_dir.thermo_path)
    kinetics = create_kinetics(model_dir.kinetics_path)

    return KineticModel(
        name=model_dir.name,
        named_species=named_species,
        thermo=thermo,
        kinetics=kinetics,
        source=source,
    )


def import_rmg_models(endpoint: str, data_path: Path = Path("rmg-models")) -> None:
    model_dirs = get_model_paths(data_path)
    for model_dir in model_dirs:
        km = create_kinetic_model(model_dir)
        response = requests.post(endpoint, data=km.json(exclude_none=True, exclude_unset=True))


def main():
    endpoint = os.getenv("POST_ENDPOINT")
    if endpoint is None:
        raise EnvironmentVariableMissing("POST_ENDPOINT not set")
    import_rmg_models(endpoint)


if __name__ == "__main__":
    main()
