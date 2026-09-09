# Veille rédaction belge

Ce dépôt construit la salle des machines d'un briefing matinal pour la rédaction belge. Il inventorie des producteurs publics, contrôle leurs accès, collecte les métadonnées de leurs flux structurés, réduit le bruit et prépare un paquet sourcé pour une analyse éditoriale distincte.

**Accès mobile :** [ouvrir le dernier briefing](https://github.com/corentinlrnt/veille-redaction-belge/blob/main/briefings/latest.md). Une page HTML autonome est également générée dans `docs/index.html` en vue de l'activation de GitHub Pages.

## Principes de cette version

- coût logiciel et hébergement : 0 € avec un dépôt GitHub public et GitHub Actions ;
- points d'accès publics uniquement, sans compte ni CAPTCHA ; un lien de presse peut mener à un article payant mais aucun paywall n'est contourné ;
- collecte limitée aux titres, liens, dates, catégories et courts extraits fournis dans les flux ;
- aucun archivage systématique du texte intégral des articles ou communiqués ;
- `robots.txt` est respecté lorsqu’il interdit explicitement un accès ;
- chaque source et chaque point d’accès possèdent un identifiant stable ;
- aucun service payant, compte tiers ou clé API ;
- aucune affirmation autonome n'est générée par la chaîne déterministe ;
- le radar lexical reste une présélection et non une validation pour diffusion ;
- le briefing final doit séparer les informations incontournables des sujets à proposer.

## Contenu

- `data/sources.csv` : producteurs d’information, provenance et modèle d'accès déclaré ;
- `data/endpoints.csv` : pages, flux ou API à tester ;
- `data/coverage_targets.csv` : groupes institutionnels attendus et références de périmètre ;
- `data/editorial_rules.json` : catégories, seuils et signaux du score explicable ;
- `data/editorial_profile.json` : mission, moteurs d'angle et contraintes du journaliste éditorial ;
- `data/editorial_output_schema.json` : contrat structuré du briefing final ;
- `docs/editorial-canvas.md` : canevas éditorial canonique, dérivé du corpus de productions JT ;
- `prompts/editorial-briefing.md` : instructions de l'étage d'analyse éditoriale ;
- `scripts/audit_coverage.py` : contrôle des manques dans le périmètre déclaré ;
- `scripts/probe_sources.py` : sonde sans dépendance Python externe ;
- `scripts/collect_items.py` : collecte résiliente des flux RSS, Atom et JSON Feed ainsi que d'adaptateurs publics explicitement validés ;
- `scripts/build_briefing.py` : dédoublonnage, classement et rendu mobile ;
- `scripts/build_editorial_packet.py` : paquet sourcé sans score destiné à l'analyse éditoriale ;
- `tests/` : tests unitaires de l'ensemble de la chaîne ;
- `briefings/` : dernier briefing Markdown et archives quotidiennes ;
- `docs/index.html` : version mobile publiée avec GitHub Pages ;
- `reports/` : rapports générés ;
- `.github/workflows/briefing.yml` : production quotidienne à 6 h, heure de Bruxelles ;
- `.github/workflows/probe.yml` : contrôle quotidien des accès à 6 h 13.

Le registre couvre désormais 221 producteurs et 283 points d'accès. Aux institutions fédérales et interfédérales prioritaires, aux 38 producteurs fonctionnels des cinq entités fédérées, aux dix provinces et aux sept institutions de l'Union européenne s'ajoutent 19 partis ou mouvements politiques, des partenaires sociaux, les cinq unions nationales de mutualités et la CAAMI/HZIV, un socle élargi consacré au fonctionnement et au contrôle de la justice, un premier réseau bilingue d'organisations de terrain, ainsi que 14 quotidiens belges, huit magazines ou médias spécialisés d'actualité, deux médias d'enquête, cinq rédactions audiovisuelles nationales ou germanophone et les 22 télévisions régionales reconnues par leurs réseaux francophone et flamand. Les 29 cibles obligatoires définissent précisément ce que le mot « couvert » signifie. La [méthode de couverture](docs/coverage-method.md) distingue ces sélections opérationnelles d'un inventaire exhaustif.

## Lancer localement

Python 3.11 ou plus récent suffit.

```bash
python scripts/audit_coverage.py
python scripts/probe_sources.py
python scripts/collect_items.py
python scripts/build_briefing.py
python scripts/build_editorial_packet.py
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
- `reports/editorial-packet.json` : candidats, provenance et profil pour l'étage éditorial ;
- `reports/editorial-prompt.md` : prompt reproductible contenant le paquet du jour ;
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

À 06:00 dans le fuseau `Europe/Brussels`, le workflow teste le code, collecte les flux, applique le score, met à jour le radar Markdown et prépare le paquet d'analyse éditoriale. Les métadonnées des sept derniers jours sont conservées afin qu'une panne ponctuelle n'efface pas les publications déjà récupérées. L'état de première apparition permet de traiter proprement les flux dépourvus de date.

La chaîne distingue désormais deux étages. Le radar déterministe réduit plusieurs milliers d'éléments à un ensemble traçable de candidats. Le paquet éditorial retire ensuite le score lexical et fournit au modèle la provenance, les limites des extraits, les huit moteurs d'angle et le contrat du futur courriel. L'appel au modèle, la validation de sa sortie et l'envoi du courriel ne sont pas encore activés.

La [méthode éditoriale](docs/editorial-method.md) documente les fenêtres temporelles, le score, le regroupement des titres et les garanties de provenance. Chaque critère est déclaré dans un fichier versionné et pourra être ajusté après les essais en rédaction.

## Contrôle des accès

Le workflow de santé est lancé à 06:13 dans le fuseau `Europe/Brussels`, été comme hiver. Une exécution manuelle est également possible depuis l’onglet **Actions**.

Il est aussi exécuté lorsqu’un registre, le programme de sonde, ses tests ou le workflow lui-même changent. Les commits qui actualisent seulement les rapports ne le relancent pas, ce qui évite une boucle.

Lorsque les rapports changent, le robot GitHub met à jour uniquement les six fichiers générés de `reports/`.

## Limites actuelles

- les pages rendues uniquement en JavaScript peuvent répondre sans exposer leurs entrées ;
- la découverte d’un flux ne garantit pas que celui-ci soit complet ou à jour ;
- les vingt-neuf cibles mesurent des socles précis et non l'exhaustivité de l'écosystème d'information belge ;
- seules les sources disposant d'un flux ou d'un adaptateur de liste explicitement validé alimentent actuellement le briefing ;
- les API REST WordPress ne livrent que les champs demandés et les adaptateurs HTML exigent des cartes `<article>` datées avec un lien et un titre ;
- les autres pages HTML et les réseaux sociaux sont sondés mais ne sont pas encore interprétés ;
- le classement lexical ne comprend pas le contexte ou l'importance réelle d'une annonce ;
- le paquet éditorial est prêt, mais aucun modèle n'est encore appelé automatiquement ;
- le courriel HTML final et son envoi ne sont pas encore implémentés ;
- la licence du dépôt doit être décidée avant publication, notamment au regard des règles de l’employeur.
