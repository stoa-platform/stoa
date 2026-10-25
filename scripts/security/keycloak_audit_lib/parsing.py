"""JSON, YAML and static kcadm payload loading."""

import json
import re
import shlex

from keycloak_audit_lib.common import json_objects

try:
    import yaml
except ImportError:
    yaml = None


def parse_representations(self, path, text, kind):
    representations = []
    if path.endswith(".json"):
        try:
            representations.append((json.loads(text), 1))
        except ValueError:
            self.add(
                path, text, "KC_PARSE", "JSON invalide ; source non évaluée.", severity="ERROR"
            )
            self.errors = True
            return
        if kind == "consumer":
            return
    else:
        representations.extend(json_objects(text))
    if path.endswith((".yaml", ".yml")) and "{{" not in text:
        if yaml is None:
            self.errors = True
            self.add(
                path,
                text,
                "KC_PARSE",
                "PyYAML indisponible ; YAML non contrôlé.",
                severity="ERROR",
            )
        else:
            try:
                representations += [(doc, 1) for doc in yaml.safe_load_all(text) if doc is not None]
            except yaml.YAMLError:
                self.errors = True
                self.add(
                    path, text, "KC_PARSE", "YAML invalide ; détails masqués.", severity="ERROR"
                )
    # kcadm -s parameters. shlex only tokenizes; never expands shell content.
    logical = re.sub(r"\\\n\s*", " ", text)
    for m in re.finditer(r"(?m)^.*(?:\bkcadm\.sh|\$KCADM).*\b(?:create|update)\b.*$", logical):
        command = m.group()
        if " -s " not in command:
            continue
        obj = {}
        try:
            words = shlex.split(command)
        except ValueError:
            self.add(
                path,
                text,
                "KC_DYNAMIC",
                "Paramètres shell non résolus ; revue requise.",
                severity="REVIEW",
            )
            continue
        for i, word in enumerate(words[:-1]):
            if word != "-s" or "=" not in words[i + 1]:
                continue
            key, value = words[i + 1].split("=", 1)
            try:
                value = json.loads(value)
            except ValueError:
                pass
            obj[key] = value
        # Determine original command line by its first physical line.
        first = command.strip().split(" -s ")[0].strip()
        lineno = next(
            (
                i
                for i, line in enumerate(text.splitlines(), 1)
                if line.strip() and line.strip().rstrip("\\").strip() in first
            ),
            1,
        )
        if obj:
            representations.append((obj, lineno))
    return representations
