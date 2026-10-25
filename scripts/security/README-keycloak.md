# Vérifications Keycloak hors ligne

Le contrôleur accompagne les configurations d’amorçage et l’outil de migration.
Python 3.11 ou supérieur et PyYAML sont requis. Aucun téléchargement n’est nécessaire.
Les tests utilisent `unittest` de la bibliothèque standard.

Depuis la racine d’une copie de travail contenant la série :

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/security -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/security/tests -p 'test_keycloak_migrate.py' -v
```

Le contrôleur effectue une lecture statique des sources sélectionnées. Il ne lance
pas les procédures inspectées. Ses résultats demandent une revue humaine et ne
valident pas l’état d’un environnement installé. Les modèles de chart doivent
également être rendus et vérifiés avec les valeurs approuvées.

L’outil de migration dispose de sa propre procédure dans
`docs/runbooks/keycloak-existing-realms-migration.md`. Les tests locaux utilisent
uniquement des données synthétiques et une frontière de transport simulée.

Les codes du contrôleur sont `0` pour un contrôle sans diagnostic bloquant,
`1` pour des diagnostics à traiter et `2` pour une erreur de lecture ou d’analyse.
Les observations de revue restent à examiner dans tous les cas.
