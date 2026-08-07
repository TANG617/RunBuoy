#!/usr/bin/env python3
"""Validate iOS deployment targets and privacy-manifest bundle membership."""

from __future__ import annotations

import argparse
import plistlib
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IOS_ROOT = REPOSITORY_ROOT / "apps" / "ios"
PROJECT_FILE = IOS_ROOT / "RunBuoy.xcodeproj" / "project.pbxproj"
APP_MANIFEST = IOS_ROOT / "RunBuoyApp" / "PrivacyInfo.xcprivacy"
WIDGET_MANIFEST = IOS_ROOT / "RunBuoyWidgets" / "PrivacyInfo.xcprivacy"

EXPECTED_APP_MANIFEST = {
    "NSPrivacyAccessedAPITypes": [
        {
            "NSPrivacyAccessedAPIType": ("NSPrivacyAccessedAPICategoryUserDefaults"),
            "NSPrivacyAccessedAPITypeReasons": ["CA92.1"],
        }
    ],
}
EXPECTED_WIDGET_MANIFEST = {
    "NSPrivacyAccessedAPITypes": [],
}


def load_plist(path: Path) -> dict[str, object]:
    with path.open("rb") as plist_file:
        return plistlib.load(plist_file)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def object_body(project: str, identifier: str) -> str:
    match = re.search(
        rf"^[ \t]*{re.escape(identifier)} /\*[^\n]*\*/ = \{{"
        rf"(.*?)^[ \t]*\}};",
        project,
        flags=re.MULTILINE | re.DOTALL,
    )
    require(match is not None, f"Missing Xcode project object {identifier}")
    return match.group(1)


def validate_project() -> None:
    project = PROJECT_FILE.read_text(encoding="utf-8")
    deployment_targets = re.findall(r"IPHONEOS_DEPLOYMENT_TARGET = ([0-9.]+);", project)
    require(
        len(deployment_targets) >= 10 and set(deployment_targets) == {"18.0"},
        "Every project, app, widget, unit-test, and UI-test configuration must "
        "set IPHONEOS_DEPLOYMENT_TARGET to 18.0",
    )

    expected_memberships = (
        (
            "A1000000000000000000001E",
            "B1000000000000000000001D",
            "D10000000000000000000003",
            "App",
        ),
        (
            "A20000000000000000000005",
            "B30000000000000000000005",
            "D20000000000000000000003",
            "Widget",
        ),
    )
    for build_file_id, file_reference_id, resources_id, target_name in expected_memberships:
        build_file = object_body(project, build_file_id)
        require(
            file_reference_id in build_file,
            f"{target_name} privacy manifest build file points to the wrong file",
        )
        file_reference = object_body(project, file_reference_id)
        require(
            "path = PrivacyInfo.xcprivacy;" in file_reference,
            f"{target_name} privacy manifest file reference is missing",
        )
        resources = object_body(project, resources_id)
        require(
            build_file_id in resources,
            f"{target_name} privacy manifest is not in its Resources build phase",
        )


def validate_source_manifests() -> None:
    require(
        load_plist(APP_MANIFEST) == EXPECTED_APP_MANIFEST,
        "App privacy manifest must declare only app-local UserDefaults reason CA92.1",
    )
    require(
        load_plist(WIDGET_MANIFEST) == EXPECTED_WIDGET_MANIFEST,
        "Widget privacy manifest must remain empty until its code uses a required-reason API",
    )


def validate_built_app(app_bundle: Path) -> None:
    widget_bundle = app_bundle / "PlugIns" / "RunBuoyWidgets.appex"
    require(app_bundle.is_dir(), f"Missing app bundle: {app_bundle}")
    require(widget_bundle.is_dir(), f"Missing embedded widget: {widget_bundle}")
    require(
        load_plist(app_bundle / "PrivacyInfo.xcprivacy") == EXPECTED_APP_MANIFEST,
        "Built app is missing the exact source privacy manifest",
    )
    require(
        load_plist(widget_bundle / "PrivacyInfo.xcprivacy") == EXPECTED_WIDGET_MANIFEST,
        "Built widget is missing the exact source privacy manifest",
    )
    require(
        load_plist(app_bundle / "Info.plist").get("MinimumOSVersion") == "18.0",
        "Built app MinimumOSVersion must be 18.0",
    )
    require(
        load_plist(widget_bundle / "Info.plist").get("MinimumOSVersion") == "18.0",
        "Built widget MinimumOSVersion must be 18.0",
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    bundle_group = parser.add_mutually_exclusive_group()
    bundle_group.add_argument(
        "--archive",
        type=Path,
        help="Optional .xcarchive whose app and embedded widget should be verified",
    )
    bundle_group.add_argument(
        "--app-bundle",
        type=Path,
        help="Optional built RunBuoy.app bundle to verify",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    validate_project()
    validate_source_manifests()
    if arguments.archive is not None:
        validate_built_app(arguments.archive / "Products" / "Applications" / "RunBuoy.app")
    elif arguments.app_bundle is not None:
        validate_built_app(arguments.app_bundle)
    print("iOS 18 deployment targets and privacy manifests are valid")


if __name__ == "__main__":
    main()
