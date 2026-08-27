# Veille rédaction belge

Ce dépôt construit une veille matinale reproductible pour la rédaction belge. Il inventorie des producteurs publics, contrôle leurs accès, collecte les métadonnées de leurs flux structurés et publie un briefing mobile de pistes politiques, judiciaires et économiques.

**Accès mobile :** [ouvrir le dernier briefing](https://github.com/corentinlrnt/veille-redaction-belge/blob/main/briefings/latest.md). Une page HTML autonome est également générée dans `docs/index.html` en vue de l'activation de GitHub Pages.

## Principes de cette version

- coût logiciel et hébergement : 0 € avec un dépôt GitHub public et GitHub Actions ;
- sources publiques uniquement, sans compte, paywall, CAPTCHA ni contournement technique ;
- collecte limitée aux titres, liens, dates, catégories et courts extraits fournis dans les flux ;
- aucun archivage systématique du texte intégral des articles ou communiqués ;
- `robots.txt` est respecté lorsqu’il interdit explicitement un accès ;
- chaque source et chaque point d’accès possèdent un identifiant stable ;
- aucun service payant, compte tiers ou clé API ;
- aucun résumé factuel autonome généré par IA ;
- le briefing reste une présélection et non une validation pour diffusion.

## Contenu

- `data/sources.csv` : producteurs d’information et provenance ;
- `data/endpoints.csv` : pages, flux ou API à tester ;
- `data/coverage_targets.csv` : groupes institutionnels attendus et références de périmètre ;
- `data/editorial_rules.json` : catégories, seuils et signaux du score explicable ;
- `scripts/audit_coverage.py` : contrôle des manques dans le périmètre déclaré ;
- `scripts/probe_sources.py` : sonde sans dépendance Python externe ;
- `scripts/collect_items.py` : collecte résiliente des flux RSS, Atom et JSON Feed ;
- `scripts/build_briefing.py` : dédoublonnage, classement et rendu mobile ;
- `tests/` : tests unitaires de l'ensemble de la chaîne ;
- `briefings/` : dernier briefing Markdown et archives quotidiennes ;
- `docs/index.html` : version mobile publiée avec GitHub Pages ;
- `reports/` : rapports générés ;
- `.github/workflows/briefing.yml` : production quotidienne à 6 h, heure de Bruxelles ;
- `.github/workflows/probe.yml` : contrôle quotidien des accès à 6 h 13.

Le registre couvre désormais deux socles publics déclarés : les institutions fédérales et interfédérales prioritaires, puis 38 producteurs fonctionnels des cinq entités fédérées. Cette deuxième couche suit notamment l'administration, les statistiques, l'emploi, la santé, l'environnement, la régulation, la concertation, l'économie, le logement et la mobilité. La [méthode de couverture](docs/coverage-method.md) explique les différences de compétences et distingue cette sélection à fort signal d'un inventaire exhaustif.

## Lancer localement

Python 3.11 ou plus récent suffit.

```bash
python scripts/audit_coverage.py
python scripts/probe_sources.py
python scripts/collect_items.py
python scripts/build_briefing.py
python -m unittest discover -s tests -v
```

Les fichiers suivants sont alors produits :

- `reports/coverage.json` : audit détaillé du périmètre déclaré ;
- `reports/coverage-matrix.csv` : matrice des cibles et de leurs lacunes ;
- `reports/coverage-summary.md` : synthèse de couverture ;
- `reports/health.json` : rapport complet, lisible par une machine ;
- `reports/access-matrix.csv` : matrice exploitable dans un tableur ;
- `reports/health-summary.md` : synthèse lisible dans GitHub.
- `reports/items.json` et `reports/items.csv` : métadonnées des éléments collectés ;
- `reports/collection-summary.md` : disponibilité et rendement des flux ;
- `reports/briefing.json` : sélection éditoriale lisible par une machine ;
- `briefings/latest.md` et `docs/index.html` : briefing courant.

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

## Production matinale

À 06:00 dans le fuseau `Europe/Brussels`, le workflow teste le code, collecte les flux, applique le score et met à jour le briefing Markdown et la page mobile. Les métadonnées des sept derniers jours sont conservées afin qu'une panne ponctuelle n'efface pas les publications déjà récupérées. L'état de première apparition permet de traiter proprement les flux dépourvus de date.

La [méthode éditoriale](docs/editorial-method.md) documente les fenêtres temporelles, le score, le regroupement des titres et les garanties de provenance. Chaque critère est déclaré dans un fichier versionné et pourra être ajusté après les essais en rédaction.

## Contrôle des accès

Le workflow de santé est lancé à 06:13 dans le fuseau `Europe/Brussels`, été comme hiver. Une exécution manuelle est également possible depuis l’onglet **Actions**.

Il est aussi exécuté lorsqu’un registre, le programme de sonde, ses tests ou le workflow lui-même changent. Les commits qui actualisent seulement les rapports ne le relancent pas, ce qui évite une boucle.

Lorsque les rapports changent, le robot GitHub met à jour uniquement les six fichiers générés de `reports/`.

## Limites actuelles

- les pages rendues uniquement en JavaScript peuvent répondre sans exposer leurs entrées ;
- la découverte d’un flux ne garantit pas que celui-ci soit complet ou à jour ;
- les quatorze cibles mesurent des socles publics précis et non l’exhaustivité de l’écosystème d’information belge ;
- seules les sources disposant d'un flux structuré explicitement validé alimentent actuellement le briefing ;
- les pages HTML sans flux et les réseaux sociaux nécessitent encore des collecteurs adaptés ;
- le classement lexical ne comprend pas le contexte ou l'importance réelle d'une annonce ;
- la licence du dépôt doit être décidée avant publication, notamment au regard des règles de l’employeur.
