# Méthode de couverture

## Ce que mesure le dépôt

Une longue liste ne permet pas de savoir ce qui manque. Le registre sépare donc trois questions :

1. **Le producteur attendu est-il recensé ?** `data/coverage_targets.csv` nomme explicitement les sources requises dans chaque groupe.
2. **Un accès public est-il configuré ?** `data/endpoints.csv` associe au moins une page, un flux ou une API active au producteur.
3. **Cet accès fonctionne-t-il aujourd’hui ?** `scripts/probe_sources.py` vérifie la réponse technique et publie son résultat sans confondre panne et absence du registre.

Le terme `complete` dans le rapport de couverture signifie uniquement que les deux premières conditions sont remplies. Il ne constitue pas un jugement éditorial et ne prétend pas couvrir toute l’actualité belge.

## Premier socle obligatoire

| Groupe | Définition opérationnelle |
| --- | --- |
| Socle exécutif fédéral | Premier ministre, SPF, Défense et SPP recensés sur le portail fédéral |
| Parlement fédéral | Chambre et Sénat |
| Exécutifs fédérés | Gouvernements wallon, bruxellois, flamand, de la Fédération Wallonie-Bruxelles et germanophone |
| Parlements fédérés | Assemblées correspondantes ; institutions flamandes communes à la région et à la communauté |
| Justice | Trois hautes juridictions et Conseil supérieur de la Justice |
| Contrôle et droits | Cour des comptes, Médiateur fédéral, APD, Unia et Myria |
| Économie | BNB, Bureau du Plan, Statbel, SPF Économie et quatre régulateurs nationaux |
| Protection sociale | SPF Sécurité sociale, ONEM, ONSS, INASTI, INAMI et Service fédéral des Pensions |
| Santé | SPF Santé, Sciensano, KCE, AFMPS et AFSCA |

Les références structurelles viennent notamment du [portail fédéral des SPF et SPP](https://www.belgium.be/fr/la_belgique/pouvoirs_publics/autorites_federales/services_publics_federaux_et_de_programmation), de la présentation du [Parlement fédéral](https://www.belgium.be/fr/la_belgique/pouvoirs_publics/autorites_federales/parlement_federal), de celle de la [Belgique fédérale](https://www.belgium.be/fr/la_belgique/pouvoirs_publics/la_belgique_federale) et de l’[organisation de la justice](https://www.belgium.be/fr/justice/organisation). Chaque cible conserve sa propre URL de référence dans le fichier de données.

## Deuxième socle : fonctions des entités fédérées

Un inventaire juridique de tous les services et organismes ne garantit pas une veille utile. Cette couche retient donc, pour chaque entité, les producteurs publics à fort signal qui permettent de surveiller des fonctions éditoriales comparables. Une cible `complete` indique que les producteurs nommés ci-dessous sont enregistrés et accessibles ; elle ne signifie pas que tous les organismes publics de l'entité sont recensés.

| Fonction suivie | Wallonie | Bruxelles | Flandre | Fédération Wallonie-Bruxelles | Communauté germanophone |
| --- | --- | --- | --- | --- | --- |
| Administration transversale | SPW | SPRB | Administration flamande | Administration FWB | Portail Ostbelgien |
| Statistiques et évaluation | IWEPS | IBSA | Statistiek Vlaanderen | — | Ostbelgien Statistik |
| Emploi | Forem | Actiris | VDAB | — | ADG |
| Santé et action sociale | AVIQ | Vivalis | Departement Zorg | ONE | — |
| Environnement | AWAC | Bruxelles Environnement | VMM | — | — |
| Régulation | CWaPE | BRUGEL | Vlaamse Nutsregulator | CSA | — |
| Concertation | CESE Wallonie | Brupartners | SERV | — | WSR |
| Économie | Wallonie Entreprendre | hub.brussels | VLAIO | — | — |
| Logement | SWL | SLRB | Wonen in Vlaanderen | — | — |
| Mobilité | TEC | STIB | De Lijn | — | — |
| Enseignement supérieur ou réseau public | — | — | — | ARES et WBE | — |

Les différences reflètent la répartition des compétences et la production publique réellement exploitable, pas une hiérarchie entre entités. La grille part des répertoires officiels des [acteurs publics wallons](https://www.wallonie.be/fr/acteurs-et-institutions/wallonie/autres-acteurs-publics-de-la-wallonie), des [administrations et institutions bruxelloises](https://be.brussels/fr/propos-de-la-region/structure-et-organisation/administrations-et-institutions-de-la-region), de la [structure de l'administration flamande](https://www.vlaanderen.be/uw-overheid/werking-en-structuur-van-de-vlaamse-overheid/structuur-van-de-vlaamse-overheid), du [portail de la Fédération Wallonie-Bruxelles](https://www.cfwb.be/) et des [compétences de la Communauté germanophone](https://www.ostbelgienlive.be/desktopdefault.aspx/tabid-506/).

## Couches suivantes

Ces familles doivent disposer de leurs propres cibles avant d’être déclarées couvertes :

- organismes spécialisés non retenus dans le socle fonctionnel des régions et communautés ;
- partis, groupes parlementaires, ministres et mandataires ;
- partenaires sociaux, associations, collectifs et mouvements de terrain ;
- provinces, grandes villes et communes selon une méthode d’échantillonnage explicite ;
- presse francophone, néerlandophone et germanophone accessible publiquement ;
- institutions européennes, pays voisins et sources internationales servant à détecter des angles transposables à la Belgique.

Les quatre sources déjà enregistrées mais hors des cibles institutionnelles — le Presscenter fédéral, Testachats, la FGTB et la CSC — restent utiles. Elles ne sont simplement pas comptées comme preuve qu’une future couche est complète.
