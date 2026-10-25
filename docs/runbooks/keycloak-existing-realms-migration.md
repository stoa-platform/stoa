# Préparation de la migration des realms Keycloak

For a new installation, use [First administrator and invitation setup](first-admin-bootstrap.md).

Ce brouillon accompagne l’amorçage et propose une procédure explicite pour les
realms existants. Aucun déploiement du chart ne lance cette procédure. Python 3.11
et la bibliothèque standard suffisent à son exécution. La compatibilité avec
Keycloak 26 doit être vérifiée dans un environnement isolé.

## Préparation

Faire approuver le périmètre, la politique et les conséquences pour les
utilisateurs. Le modèle fourni est un exemple à compléter et à faire relire.
Il ne représente aucun environnement installé.

Préparer un accès administratif indépendant, une sauvegarde approuvée et une
restauration éprouvée. Suspendre les autres écritures de configuration pendant
l’intervention. Le journal de procédure ne remplace pas une sauvegarde complète.

Vérifier l’exhaustivité de l’inventaire et la provenance des données d’identité
avec les responsables concernés. Préparer un répertoire privé pour les plans et
journaux. Le matériel d’authentification passe exclusivement par le canal protégé
approuvé ; il ne doit figurer dans aucun argument ni journal public.

## Simulation et application

Consulter l’aide locale pour les arguments disponibles :

```bash
python3 scripts/security/keycloak_migrate.py --help
```

La simulation est le mode par défaut. Conserver son plan dans le répertoire
privé, le faire relire, puis utiliser ce plan pour une application explicitement
autorisée. Chaque invocation doit utiliser un nouveau journal. Les plans et
journaux restent privés et ne doivent être copiés ni dans le dépôt ni dans un ticket.

L’outil vérifie les préconditions et relit les objets après modification.
Il n’offre ni transaction globale ni verrou distribué. Une interruption peut
laisser une application partielle. Conserver les journaux, rétablir les
conditions d’intervention et refaire une simulation avant toute reprise.

## Retour arrière et recette

Le retour arrière demande une action explicite et commence lui aussi par une
simulation. Après plusieurs reprises, traiter les journaux d’exécution dans
l’ordre inverse. Faire approuver les conséquences pour les utilisateurs avant
la restauration. Les effets dépassant la configuration demandent une procédure
complémentaire avec les responsables de l’environnement.

La recette isolée doit couvrir les parcours approuvés, les consommateurs,
les identités humaines et techniques, la conservation des données et la reprise.
Les tests hors ligne couvrent les contrats du code et le transport simulé ; ils
ne remplacent pas cette recette ni un essai de restauration.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s scripts/security/tests -p 'test_keycloak_migrate.py' -v
```

Les codes de sortie sont `0` pour une simulation valide ou une application
vérifiée, `2` pour un arrêt à examiner et `130` pour une interruption. Une
simulation valide peut proposer des changements : son code de sortie ne suffit
pas à attester la conformité de l’environnement.
