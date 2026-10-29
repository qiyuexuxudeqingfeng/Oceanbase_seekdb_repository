#!/usr/bin/env python3
"""Adapt the bundled OBD plugins to this engine revision.

OBD is shipped pre-built inside ``deps/3rd`` and its seekdb plugin is written
for a newer engine than the one this repository builds.  Two adaptations are
required before ``obd cluster start`` can bring the instance up:

1. ``start_pre.py`` renders every default parameter it knows.  The engine
   validates each ``--parameter`` name against ``rust/config/parameters.yaml``
   and exits on the first unknown one, so the rendered set has to be narrowed
   down to the names this revision actually declares.
2. ``display.py`` is the last step of ``obd cluster start`` and the shipped
   implementation polls ``oceanbase.__all_server`` forever when the table is
   empty.  The instance is already serving SQL at that point, so the step never
   returns and ``obd cluster start`` hangs.  A bounded replacement is appended
   to the module; the later definition wins.

Both edits are idempotent, so the script can run before every prepare/deploy.
"""

import argparse
import re
import sys
from pathlib import Path

PLUGIN_RELATIVE_PATH = Path("deps/3rd/usr/obd/plugins/seekdb/1.0.0")
DISPLAY_PATCH_PATH = Path(__file__).with_name("obd_display_patch.py")

ENGINE_PARAMS_HEADER_MARKER = "ENGINE_PARAMS = frozenset("
START_PRE_OLD = (
    "        if key not in not_cmd_opt and key not in not_opt_lite_str"
    " and not key.startswith('ocp_meta_tenant_'):"
)
START_PRE_NEW = (
    "        if key not in not_cmd_opt and key not in not_opt_lite_str"
    " and not key.startswith('ocp_meta_tenant_') and key in ENGINE_PARAMS:"
)
START_PRE_ANCHOR = "from collections import OrderedDict\n"
DISPLAY_PATCH_MARKER = "# BOUNDED_DISPLAY_PATCH"


class PatchError(RuntimeError):
    pass


def engine_parameter_names(base_dir):
    registry_path = base_dir / "rust" / "config" / "parameters.yaml"
    if not registry_path.is_file():
        raise PatchError("missing engine parameter registry: {}".format(registry_path))
    registry = registry_path.read_text(encoding="utf-8")
    names = set(
        re.findall(r"^-\s+name:\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", registry, re.M)
    )
    if len(names) < 200:
        raise PatchError(
            "unexpected engine parameter registry size: {}".format(len(names))
        )
    return names


def restrict_parameters(plugin_dir, names):
    start_pre = plugin_dir / "start_pre.py"
    text = start_pre.read_text(encoding="utf-8")
    if ENGINE_PARAMS_HEADER_MARKER in text:
        return "already restricted"
    if START_PRE_ANCHOR not in text:
        raise PatchError("start_pre.py has no OrderedDict import anchor")
    header = "ENGINE_PARAMS = frozenset(%r)\n" % (sorted(names),)
    text = text.replace(START_PRE_ANCHOR, START_PRE_ANCHOR + "\n" + header, 1)
    if START_PRE_OLD not in text:
        raise PatchError("start_pre.py parameter filter is not in the expected shape")
    text = text.replace(START_PRE_OLD, START_PRE_NEW, 1)
    start_pre.write_text(text, encoding="utf-8")
    return "restricted to {} engine parameters".format(len(names))


def bound_display(plugin_dir):
    display = plugin_dir / "display.py"
    text = display.read_text(encoding="utf-8")
    if DISPLAY_PATCH_MARKER in text:
        return "already bounded"
    patch = DISPLAY_PATCH_PATH.read_text(encoding="utf-8")
    display.write_text(text + "\n" + patch, encoding="utf-8")
    return "bounded the display step"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "base_dir",
        nargs="?",
        default=str(Path(__file__).resolve().parents[2]),
        help="repository root that contains deps/3rd",
    )
    args = parser.parse_args(argv)
    base_dir = Path(args.base_dir).resolve()
    plugin_dir = base_dir / PLUGIN_RELATIVE_PATH
    if not plugin_dir.is_dir():
        print("obd seekdb plugin not present at {}; nothing to patch".format(plugin_dir))
        return 0
    try:
        names = engine_parameter_names(base_dir)
        print("OBD parameter filter: " + restrict_parameters(plugin_dir, names))
        print("OBD display step: " + bound_display(plugin_dir))
    except PatchError as exc:
        print("failed to adapt the OBD plugin: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
