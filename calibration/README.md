# Calibration éditoriale

Ce répertoire reçoit les réponses JSON brutes produites pendant la phase de
calibration. Il ne contient ni doctrine cachée ni logique de rendu.

Une réponse doit être enregistrée sous
`calibration/responses/AAAA-MM-JJ.json`. Le workflow dédié la refuse si elle ne
respecte pas le schéma, si sa date ne correspond pas au paquet quotidien, si
un lien n'était pas présent dans ce paquet ou si une rubrique « repéré hors
presse » ne s'appuie pas sur la voie primaire.

Après validation, les sorties lisibles et leurs métadonnées sont publiées dans
`briefings/editorial/` et `reports/`. Un formulaire JSON est créé dans
`calibration/feedback/` avec des identifiants stables pour chaque proposition.
Il permet de noter séparément utilité, originalité, faisabilité et valeur des
sources, puis de choisir `a_defendre`, `a_garder` ou `a_jeter`.

Ces retours restent distincts du profil et du prompt : ils pourront être
analysés après plusieurs éditions, sans transformer automatiquement une
réaction isolée en règle définitive.
