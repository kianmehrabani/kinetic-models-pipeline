import json
import os
from pathlib import Path

from dotenv import load_dotenv
import requests
from datamodel_code_generator import InputFileType, generate

load_dotenv()

class MissingEnvironmentVariable(Exception):
    pass

def get_json_schema(url) -> str:
    content = requests.get(url).json()
    return json.dumps(content)


def generate_models(endpoint: str, path: Path = Path("models.py")) -> None:
    json_schema = get_json_schema(endpoint)
    generate(
        json_schema,
        input_file_type=InputFileType.OpenAPI,
        input_filename="openapi.json",
        output=path,
    )

if __name__ == "__main__":
    endpoint = os.getenv("SCHEMA_ENDPOINT")
    if endpoint is None:
        raise MissingEnvironmentVariable("SCHEMA_ENDPOINT is not set")
    generate_models(endpoint)
