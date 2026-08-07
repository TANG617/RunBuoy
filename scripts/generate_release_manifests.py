"""Generate release-time CLI and iOS dependency/source manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
IOS_ROOT = ROOT / "apps" / "ios"
IOS_SOURCE_SUFFIXES = {
    ".entitlements",
    ".json",
    ".pbxproj",
    ".plist",
    ".png",
    ".strings",
    ".swift",
    ".xcscheme",
    ".xcstrings",
    ".xctestplan",
    ".xcworkspacedata",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def package_ref(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(name)}@{quote(version)}"


def cli_version() -> str:
    source = (ROOT / "cli" / "src" / "runbuoy" / "__init__.py").read_text()
    match = re.search(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
    if match is None:
        raise ValueError("CLI version is missing")
    return match.group(1)


def cli_sbom(source_revision: str) -> dict[str, Any]:
    lock = tomllib.loads((ROOT / "cli" / "uv.lock").read_text())
    packages = {item["name"]: item for item in lock["package"]}
    root_package = packages["runbuoy"]
    selected = {"runbuoy"}
    pending = [dependency["name"] for dependency in root_package.get("dependencies", [])]
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        selected.add(name)
        pending.extend(item["name"] for item in packages[name].get("dependencies", []))

    components: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    version = cli_version()
    root_ref = package_ref("runbuoy", version)
    for name in sorted(selected - {"runbuoy"}):
        package = packages[name]
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": package_ref(name, package["version"]),
            "name": name,
            "version": package["version"],
            "purl": package_ref(name, package["version"]),
        }
        source_hash = package.get("sdist", {}).get("hash")
        if source_hash and source_hash.startswith("sha256:"):
            component["hashes"] = [{"alg": "SHA-256", "content": source_hash[7:]}]
        components.append(component)
        dependencies.append(
            {
                "ref": package_ref(name, package["version"]),
                "dependsOn": sorted(
                    package_ref(dependency["name"], packages[dependency["name"]]["version"])
                    for dependency in package.get("dependencies", [])
                    if dependency["name"] in selected
                ),
            }
        )

    dependencies.append(
        {
            "ref": root_ref,
            "dependsOn": sorted(
                package_ref(item["name"], packages[item["name"]]["version"])
                for item in root_package.get("dependencies", [])
            ),
        }
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"runbuoy-cli:{version}:{source_revision}")
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "runbuoy",
                "version": version,
                "purl": root_ref,
            },
            "properties": [{"name": "runbuoy:source-revision", "value": source_revision}],
        },
        "components": components,
        "dependencies": sorted(dependencies, key=lambda item: item["ref"]),
    }


def swift_dependencies() -> list[dict[str, str]]:
    manifests = sorted(IOS_ROOT.rglob("Package.resolved"))
    dependencies: list[dict[str, str]] = []
    for manifest in manifests:
        value = json.loads(manifest.read_text())
        for pin in value.get("pins", value.get("object", {}).get("pins", [])):
            state = pin.get("state", {})
            dependencies.append(
                {
                    "identity": pin.get("identity", pin.get("package", "unknown")),
                    "location": pin.get("location", pin.get("repositoryURL", "unknown")),
                    "revision": state.get("revision", "unknown"),
                    "version": state.get("version", state.get("branch", "unknown")),
                }
            )
    return sorted(dependencies, key=lambda item: (item["identity"], item["location"]))


def ios_manifest(source_revision: str) -> dict[str, Any]:
    sources = sorted(
        path
        for path in IOS_ROOT.rglob("*")
        if path.is_file()
        and path.suffix in IOS_SOURCE_SUFFIXES
        and "VerificationScreenshots" not in path.parts
    )
    imports: set[str] = set()
    import_pattern = re.compile(r"^import\s+([A-Za-z0-9_]+)\s*$", re.MULTILINE)
    for source in (path for path in sources if path.suffix == ".swift"):
        imports.update(import_pattern.findall(source.read_text()))

    project = (IOS_ROOT / "RunBuoy.xcodeproj" / "project.pbxproj").read_text()
    deployment_targets = sorted(
        set(re.findall(r"IPHONEOS_DEPLOYMENT_TARGET = ([0-9.]+);", project))
    )
    package_manifests = sorted(
        path.relative_to(ROOT).as_posix() for path in IOS_ROOT.rglob("Package.resolved")
    )
    return {
        "schema_version": 1,
        "component": "RunBuoy iOS app and widget source",
        "source_revision": source_revision,
        "deployment_targets": deployment_targets,
        "source_files": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)} for path in sources
        ],
        "swift_package_manifests": package_manifests,
        "third_party_swift_packages": swift_dependencies(),
        "apple_sdk_imports": sorted(imports),
        "dependency_note": (
            "No Package.resolved file is present; the listed imports are Apple SDK frameworks."
            if not package_manifests
            else "Third-party Swift packages are pinned by the listed Package.resolved files."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-revision", default="unknown")
    parser.add_argument("--component", choices=("all", "cli", "ios"), default="all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.component in {"all", "cli"}:
        write_json(args.output_dir / "runbuoy-cli.cdx.json", cli_sbom(args.source_revision))
    if args.component in {"all", "ios"}:
        write_json(
            args.output_dir / "runbuoy-ios-source-manifest.json",
            ios_manifest(args.source_revision),
        )


if __name__ == "__main__":
    main()
