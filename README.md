# Veille rédaction belge — infrastructure d’accès

Ce dépôt constitue la première brique d’une veille matinale pour la rédaction belge. Il ne sélectionne pas encore les sujets et ne rédige aucun résumé : il inventorie des producteurs d’information publics, teste leurs points d’accès et publie un rapport de santé traçable.

## Principes de cette version

- coût logiciel et hébergement : 0 € avec un dépôt GitHub public et GitHub Actions ;
- sources publiques uniquement, sans compte, paywall, CAPTCHA ni contournement technique ;
- collecte limitée aux métadonnées utiles au contrôle d’accès ;
- aucun archivage systématique du texte intégral des articles ou communiqués ;
- `robots.txt` est respecté lorsqu’il interdit explicitement un accès ;
- chaque source et chaque point d’accès possèdent un identifiant stable ;
- les résultats techniques ne constituent ni une validation juridique ni une recommandation éditoriale.

## Contenu

- `data/sources.csv` : producteurs d’information et provenance ;
- `data/endpoints.csv` : pages, flux ou API à tester ;
- `data/coverage_targets.csv` : groupes institutionnels attendus et références de périmètre ;
- `scripts/audit_coverage.py` : contrôle des manques dans le périmètre déclaré ;
- `scripts/probe_sources.py` : sonde sans dépendance Python externe ;
- `tests/` : tests unitaires du détecteur ;
- `reports/` : rapports générés ;
- `.github/workflows/probe.yml` : exécution quotidienne vers 6 h, heure de Bruxelles.

Le registre couvre désormais un premier socle public déclaré : départements fédéraux, parlements et exécutifs des entités fédérées, hautes juridictions, contre-pouvoirs, régulateurs économiques, sécurité sociale et agences de santé. La [méthode de couverture](docs/coverage-method.md) distingue ce socle des couches encore à construire : partis et mandataires, acteurs de terrain, pouvoirs locaux, médias belges et sources internationales.

## Lancer localement

Python 3.11 ou plus récent suffit.

```bash
python scripts/audit_coverage.py
python scripts/probe_sources.py
python -m unittest discover -s tests -v
```

Les fichiers suivants sont alors produits :

- `reports/coverage.json` : audit détaillé du périmètre déclaré ;
- `reports/coverage-matrix.csv` : matrice des cibles et de leurs lacunes ;
- `reports/coverage-summary.md` : synthèse de couverture ;
- `reports/health.json` : rapport complet, lisible par une machine ;
- `reports/access-matrix.csv` : matrice exploitable dans un tableur ;
- `reports/health-summary.md` : synthèse lisible dans GitHub.

Une cible de couverture est complète si toutes les sources qu’elle exige sont enregistrées et possèdent au moins un point d’accès actif. Cela ne signifie pas que ces accès répondent : la sonde de santé le mesure séparément. Une cible obligatoire incomplète ou une erreur de schéma provoque un échec explicite. Une erreur sur un site distant est enregistrée sans faire échouer l’ensemble du traitement.

## Lire les statuts

| Statut | Sens |
| --- | --- |
| `ok` | La ressource a répondu et son format a été détecté. |
| `blocked_by_robots` | `robots.txt` interdit explicitement la sonde sur ce chemin. |
| `http_error` | Le serveur a répondu avec un code d’erreur HTTP. |
| `network_error` | La connexion, le DNS ou le délai a échoué. |
| `parse_error` | Le contenu annoncé comme structuré n’a pas pu être analysé. |
| `unsupported` | Le format reçu n’est pas encore reconnu. |

`robots_status=missing` signifie seulement qu’aucun fichier `robots.txt` n’a été trouvé. `robots_status=unknown` signifie qu’il n’a pas pu être contrôlé. Ni l’un ni l’autre ne vaut autorisation juridique.

## Ajouter une source

1. Ajouter le producteur dans `data/sources.csv` avec un `source_id` unique.
2. Ajouter au moins un accès public dans `data/endpoints.csv`.
3. Si elle appartient au socle obligatoire, l’ajouter à la cible correspondante dans `data/coverage_targets.csv`.
4. Indiquer la date du dernier contrôle manuel et la portée du contenu.
5. Lancer l’audit, les tests et la sonde.
6. Vérifier les conditions d’utilisation avant toute collecte plus riche que ce contrôle de métadonnées.

Les flux découverts automatiquement dans une page HTML apparaissent dans `discovered_feeds`. Ils restent des candidats : ils ne sont ajoutés au registre qu’après contrôle manuel.

## Automatisation GitHub

Le workflow est lancé à 06:13 dans le fuseau `Europe/Brussels`, été comme hiver. Le décalage de treize minutes évite la période la plus chargée des tâches planifiées. Une exécution manuelle est également possible depuis l’onglet **Actions**.

Il est aussi exécuté lorsqu’un registre, le programme de sonde, ses tests ou le workflow lui-même changent. Les commits qui actualisent seulement les rapports ne le relancent pas, ce qui évite une boucle.

Lorsque les rapports changent, le robot GitHub met à jour uniquement les six fichiers générés de `reports/`.

## Limites actuelles

- les pages rendues uniquement en JavaScript peuvent répondre sans exposer leurs entrées ;
- la découverte d’un flux ne garantit pas que celui-ci soit complet ou à jour ;
- les neuf cibles mesurent un socle public précis et non l’exhaustivité de l’écosystème d’information belge ;
- aucun dédoublonnage, classement éditorial ou résumé n’est encore effectué ;
- la licence du dépôt doit être décidée avant publication, notamment au regard des règles de l’employeur.
