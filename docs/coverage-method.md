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
| Hautes juridictions et gouvernance judiciaire | Cour constitutionnelle, Conseil d'État, Cour de cassation et Conseil supérieur de la Justice |
| Fonctionnement judiciaire | Ministère public et Collège des cours et tribunaux |
| Contrôle et droits | Cour des comptes, Médiateur fédéral, APD, Unia, Myria, CCSP, IFDH et Comité P |
| Professions de la justice | AVOCATS.BE et Orde van Vlaamse Balies, identifiés comme ordres professionnels et non comme sources publiques neutres |
| Économie | BNB, Bureau du Plan, Statbel, SPF Économie et quatre régulateurs nationaux |
| Protection sociale | SPF Sécurité sociale, ONEM, ONSS, INASTI, INAMI et Service fédéral des Pensions |
| Santé | SPF Santé, Sciensano, KCE, AFMPS et AFSCA |

Les références structurelles viennent notamment du [portail fédéral des SPF et SPP](https://www.belgium.be/fr/la_belgique/pouvoirs_publics/autorites_federales/services_publics_federaux_et_de_programmation), de la présentation du [Parlement fédéral](https://www.belgium.be/fr/la_belgique/pouvoirs_publics/autorites_federales/parlement_federal), de celle de la [Belgique fédérale](https://www.belgium.be/fr/la_belgique/pouvoirs_publics/la_belgique_federale) et de l’[organisation de la justice](https://www.belgium.be/fr/justice/organisation). Le périmètre justice est précisé par les sites du [Ministère public](https://www.om-mp.be/fr), du [Collège des cours et tribunaux](https://www.rechtbanken-tribunaux.be/fr/college), du [CCSP](https://ccsp.belgium.be/), de l'[IFDH](https://institutfederaldroitshumains.be/fr), du [Comité P](https://comitep.be/index.html), d'[AVOCATS.BE](https://www.avocats.be/) et de l'[OVB](https://www.ordevanvlaamsebalies.be/). Chaque cible conserve sa propre URL de référence dans le fichier de données.

Ce socle justice reste une sélection opérationnelle. Il ne transforme pas chaque communiqué de parquet en piste : les listes du Ministère public sont enregistrées mais ne sont pas extraites tant qu'un filtre fiable n'écarte pas les faits divers sans portée sociétale. Les pages sans flux structuré ou balisage sémantique sûr sont seulement sondées.

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

## Troisième couche : acteurs politiques et terrain

Cette couche ne traite pas les organisations intéressées comme des autorités neutres. Elle garantit seulement qu'elles sont surveillées de manière équilibrée et que leur statut reste visible dans chaque piste.

| Groupe | Définition opérationnelle |
| --- | --- |
| Partis nationaux | Onze producteurs représentés au niveau fédéral ; DéFI est ajouté hors cible comme producteur régional |
| Partis du Parlement flamand | Les huit choix proposés par le filtre officiel des représentants dont Team Fouad Ahidar |
| Partis germanophones | Les six partis représentés au Parlement de la Communauté germanophone |
| Partenaires sociaux | FGTB, CSC, CGSLB, FEB, UCM et UNIZO reliés par le Conseil national du Travail ; Voka est suivi en complément régional |
| Pauvreté | Réseau wallon de lutte contre la pauvreté et Netwerk tegen Armoede |
| Mutualités | Les cinq unions nationales et la CAAMI/HZIV ; cette cible ne prétend pas recenser tous les régimes particuliers d'assurance |

Les références de périmètre sont la [Chambre](https://www.lachambre.be/), le [filtre des représentants du Parlement flamand](https://www.vlaamsparlement.be/nl/vlaamse-volksvertegenwoordigers-in-het-Vlaams-Parlement), le [Parlement de la Communauté germanophone](https://www.pdg.be/), les [liens du Conseil national du Travail](https://cnt-nar.be/fr/liens), les [réseaux reconnus par le Service de lutte contre la pauvreté](https://luttepauvrete.be/service/reseaux-belges-de-lutte-contre-la-pauvrete/) et l'[annuaire des mutualités de l'INAMI](https://www.inami.fgov.be/fr/professionnels/autres-professionnels/mutualites/contactez-les-mutualites).

Les organisations de défense des droits et de l'environnement enregistrées forment un premier noyau éditorial, mais ne sont pas déclarées exhaustives faute de répertoire de référence unique. Les familles encore à construire sont notamment les provinces, villes et communes, la presse accessible publiquement, les institutions européennes et les pays voisins servant à détecter des angles transposables à la Belgique.
