"""Static mutation and sensitive-output lexical checks."""

import re


def lexical_checks(self, path, text):
    # Explicit lexical checks catch mutations not represented as full realms.
    normal = text.replace('\\"', '"')
    for n, line in enumerate(normal.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            continue
        if re.search(r"\bregistrationAllowed\s*=\s*true\b", line):
            self.add(path, text, "KC_REGISTRATION", "Commande ouvrant l’auto-inscription.", start=n)
        if re.search(r"\bresetPasswordAllowed\s*=\s*true\b", line):
            self.add(path, text, "KC_RESET", "Commande ouvrant la récupération de compte.", start=n)
        for key, rule in [
            ("directAccessGrantsEnabled", "KC_DIRECT_GRANT"),
            ("implicitFlowEnabled", "KC_IMPLICIT"),
        ]:
            if re.search(r"\b" + key + r'["\x27]?\s*[:=]\s*(?:true|True)\b', line):
                self.add(
                    path,
                    text,
                    rule,
                    "Flux hérité activé dans une mutation statique.",
                    key,
                    n,
                    dev_warning=(rule == "KC_DIRECT_GRANT"),
                )
        if re.search(
            r"(?i)^\s*(?:echo|print|log_?\w*)\b.*(?<!\\)\$(?:\{)?(?:\w*(?:SECRET|PASSWORD|PWD)|(?:ADMIN_|ACCESS_)?TOKEN)\b",
            line,
        ):
            self.add(
                path,
                text,
                "KC_SECRET_OUTPUT",
                "Affichage potentiel de valeur sensible [MASQUÉE].",
                start=n,
                severity="REVIEW" if "|" in line else "HIGH",
            )
        if re.search(r"(?i)(?:PASSWORD|SECRET|_PWD|_PASS)\w*\s*=.*\$\{[^}]*:-[^}]+\}", line):
            match = re.search(r"\$\{([A-Z_]+):-", line)
            guard = ': "${' + match[1] + ":?" if match else None
            guarded = guard and guard in "\n".join(normal.splitlines()[: n - 1])
            self.add(
                path,
                text,
                "KC_SECRET_FALLBACK",
                "Secours littéral [MASQUÉ] ; garde explicite présente."
                if guarded
                else "Valeur sensible de secours littérale [MASQUÉE].",
                start=n,
                severity="REVIEW" if guarded else "HIGH",
                dev_warning=not guarded,
            )
        if re.search(r"^\s*create_user\s+", line):
            self.add(
                path,
                text,
                "KC_TEST_USERS",
                "Commande de création de compte de test ; arguments masqués.",
                start=n,
                dev_warning=True,
            )
        if re.search(r"(?:curl|kcadm|KCADM).*(?:reset-password|/users)", line):
            self.add(
                path,
                text,
                "KC_USER_MUTATION",
                "Mutation de comptes ; vérifier isolation dev/prod.",
                start=n,
                severity="REVIEW",
            )
        assignment = re.search(
            r'^\s*(?:export\s+)?[A-Z_]*(?:PASSWORD|SECRET|_PWD|_PASS)[A-Z_]*=["\x27]([^"\x27]+)["\x27]\s*$',
            line,
        )
        if (
            assignment
            and not re.search(r"\$|REPLACE_|CHANGE_ME|<[^>]+>", assignment[1])
            and not re.search(r"POLICY\s*=", line)
        ):
            self.add(
                path,
                text,
                "KC_HARDCODED_SECRET",
                "Affectation sensible littérale [MASQUÉE].",
                start=n,
                dev_warning=True,
            )
