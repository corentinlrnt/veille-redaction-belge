# Méthode éditoriale du briefing

## Rôle du système

Le briefing est un outil de présélection. Il ne valide pas un fait pour diffusion, ne remplace pas la vérification journalistique et ne produit pas de synthèse factuelle autonome. Chaque piste conserve le titre, la date, le producteur, le lien et, lorsqu'il existe, un court extrait fourni par le flux source.

## Fenêtre observée

- la collecte conserve sept jours de métadonnées pour résister aux pannes temporaires ;
- le briefing retient normalement les publications des 36 dernières heures ;
- une date future située dans les 36 heures peut être conservée pour un agenda ;
- un élément sans date est ignoré lors du premier inventaire puis n'est proposé que lorsqu'il apparaît réellement pour la première fois dans un flux déjà connu.

## Score explicable

Le score additionne des critères déclarés dans `data/editorial_rules.json` :

1. responsabilité du producteur : parlement, juridiction, régulateur, institut statistique, partenaire social, organisme public ;
2. nature du contenu : décision, arrêt, alerte, statistique, rapport, étude, avis, agenda ou communiqué ;
3. fraîcheur de la publication ;
4. signaux lexicaux multilingues : décision publique, effet concret sur la population, données, contrôle et droits, changement ou échéance ;
5. minoration des contenus promotionnels, sportifs ou culturels sans enjeu public explicite.

Chaque entrée affiche les raisons qui ont effectivement contribué à son score. Les règles sont modifiables sans changer le programme et feront l'objet des essais éditoriaux.

## Classement

Les éléments sont répartis entre trois domaines correspondant au service :

- politiques publiques et société, au sens large et jusqu'à leurs effets sur le terrain ;
- justice, droits et contrôle public ;
- économie, emploi et consommateurs.

Les titres lexicalement très proches sont regroupés. Le rapprochement ne constitue pas une affirmation que deux publications traitent exactement du même fait. Trois publications au maximum par producteur peuvent entrer dans un briefing afin d'éviter qu'un flux prolifique n'écrase les autres.

## Garanties de provenance

- aucun élément ne peut être affiché sans URL publique ;
- les extraits sont identifiés comme fournis par la source ;
- aucun texte intégral n'est archivé ;
- les erreurs de collecte restent visibles dans `reports/collection-summary.md` ;
- une panne n'efface pas immédiatement les éléments datés encore valides récupérés lors du passage précédent ;
- `robots.txt` est contrôlé avant la collecte.

## Limites actuelles

La collecte exploite les flux RSS, Atom et JSON Feed explicitement enregistrés. Les pages HTML sans flux et les réseaux sociaux ne sont pas encore interprétés. Le score lexical ne comprend ni l'ironie, ni le contexte politique, ni la portée réelle d'une annonce. Ces limites sont affichées dans chaque briefing.
