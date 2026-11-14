# Revue critique de DodOS : `DIRECTION.md` et `core.wit`

Revue du 14 novembre 2026, sur l'état du dépôt au commit `20f18ff`. Les numéros de ligne (« l. ») renvoient à `DIRECTION.md`, sauf mention de `core.wit`.

Chaque constat porte une mention :

- **Confirmé** : vérifié dans le texte des deux fichiers, ou auprès d'une source citée en fin de rapport.
- **Suspecté** : conclusion d'un raisonnement de conception, qu'aucun essai n'a encore éprouvée.

Les faits que je cite sans les avoir revérifiés sont marqués « de mémoire ». Je n'ai pas rouvert les lignes « Décidé », sauf là où j'ai trouvé une contradiction ou une erreur de fait ; ces cas sont signalés comme tels.

## Verdict

Les faits vérifiables du document sont presque tous exacts : sur une quarantaine contrôlés, je n'en ai trouvé aucun d'inventé. Les faiblesses sont dans la conception et dans le plan, et cinq d'entre elles comptent plus que les autres.

1. **L'instantané de processus porte six sections et n'est pas conçu.** La coupure de courant, la panique d'un noyau, la pression mémoire, le démarrage en deux secondes, la mise à jour et le déplacement entre appareils en dépendent tous, alors qu'il n'est inscrit qu'au réservoir d'idées (« rien de décidé »). Il n'a aucune définition pour le code natif, qui porte le moteur web, les services, les pilotes et l'inférence.
2. **La structure multi-cœur du noyau n'est pas tranchée, et les propositions se contredisent.** « Groupe de cœurs » a deux sens opposés dans le document. La règle « un thread passif par cœur » pour chaque service fait de tout service un processus multithread étalé sur tous les cœurs : le cas déclaré « ouvert » devient le cas général. L'arbre de dérivation des capacités est un état global, que le document ne traite pas.
3. **L'oracle seL4 ne juge presque rien de ce que ce noyau a de propre.** Un noyau par cœur, les objets mémoire, l'ordonnancement par échéance, l'IOMMU, la tâche et les étiquettes n'existent pas dans seL4. Le vrai juge est le modèle exécutable, qui n'apparaît dans aucun contrôle. Le chemin rapide d'IPC, écrit en Zig, échappe à tous les outils de preuve cités.
4. **Le modèle de sécurité de l'agent ne tient pas avec `core.wit` tel qu'il est écrit.** La parade au mensonge sur la classe d'effet suppose des capacités remises appel par appel ; le monde `app` remet tout au lancement. La classe d'effet mélange deux axes. La règle de confirmation, telle qu'écrite, rend l'étiquette de provenance sans effet. C'est la thèse du produit.
5. **Le calendrier n'est pas crédible côté noyau et matériel, et l'ordre de construction contient une erreur.** La bibliothèque standard de Rust et mlibc sont placées après le triangle Vulkan, alors que NVK en a besoin. Je propose une alpha vers octobre 2027 plutôt qu'au deuxième trimestre, avec le détail plus bas.

## Constats critiques

### 1. L'instantané de processus : mécanisme porteur, jamais conçu

**Où.** Inscrit au réservoir d'idées, l. 495, sous le titre « rien de décidé ». Utilisé comme acquis aux l. 205-206 (coupure : « les processus sont pris en instantané à intervalle régulier »), l. 210 (reprise après panique d'un noyau), l. 221 (arrêt), l. 237 (une zone de stockage lui est réservée), l. 388 (« shell rendu depuis son instantané »), l. 469 et 590 (pression mémoire), l. 485 (déplacement d'une surface), l. 527 et 540.

**Statut : confirmé** pour l'écart entre le statut et l'usage. **Suspecté** pour les points de faisabilité ci-dessous.

**Ce qui manque.**

- *Le code natif.* L'argument du document est que l'état d'un composant Wasm est explicite (mémoire linéaire, tables, handles). Cela ne dit rien de Ladybird, des services Rust, des pilotes Linux émulés ni de llama.cpp, qui sont natifs. Les figer revient à écrire un point de reprise complet de processus, avec l'état du noyau, du GPU et des périphériques. Le document n'en parle pas.
- *Le Wasm lui-même.* L'état n'est explicite qu'entre deux appels. Pendant un appel asynchrone, la pile native contient des adresses de retour et des registres dans la disposition propre au code compilé. Un instantané pris à ce moment ne se relit qu'avec exactement le même code machine. « Reprise exacte après une mise à jour » (l. 495) échoue donc dès que le compilateur change, et le déplacement d'un desktop x86 vers un téléphone ARM (l. 485) échoue toujours.
- *La cohérence entre processus.* Des instantanés pris processus par processus, à des instants différents, ne forment pas un état cohérent : un client restauré tient un handle que le service a déjà détruit, ou attend une réponse déjà envoyée. EROS et KeyKOS, cités comme ancêtres, prenaient pour cette raison un point de reprise de tout le système (de mémoire). Les connexions réseau et l'état du GPU ne se restaurent pas du tout.
- *Le coût.* Figer tous les processus toutes les quelques secondes demande de suivre les pages modifiées et d'écrire en continu sur le disque. Aucune porte ne borne ce coût, ni l'usure du disque.

**Pourquoi c'est grave.** La promesse « on ne tue jamais sans instantané » (l. 590), la reprise après panique et la porte de démarrage à deux secondes reposent dessus. Si le mécanisme se révèle limité aux composants Wasm au repos, ces trois sections sont à réécrire.

**Recommandation.** Définir la version 1 ainsi, et l'écrire :

- Une application sauve son état elle-même : deux exports `suspend` et `resume` dans le monde `app`, l'état allant dans sa collection `home`.
- Un instantané Wasm automatique seulement pour un composant au repos (aucun appel en cours), à mesurer par un essai d'une semaine avec Wasmtime.
- Aucun instantané pour le natif : un service redémarre et recharge son état depuis le stockage, ce que le principe « crash-only » (l. 203) exige déjà.
- Une politique de pression mémoire qui fonctionne sans instantané, puisqu'il faudra bien tuer un processus natif.

### 2. La structure multi-cœur : trois propositions incompatibles et un problème non vu

**Où.** l. 38, 208, 216, 424, 436-437, 636, 682-683, 698.

**Statut : confirmé** pour les contradictions de texte. **Suspecté** pour les conséquences techniques.

**Le terme « groupe de cœurs » a deux sens.**

- l. 437 et 636 : plusieurs noyaux, un par cœur, qui tiennent l'espace d'adresses cohérent *par messages*. La l. 216 retient ce sens parce qu'il se prête à la reprise d'un noyau.
- l. 38 et 698 : *un seul noyau* partagé par le groupe, « avec un verrou court ».

Ces deux conceptions ont des conséquences opposées. La première garde « aucun état partagé » et paie chaque défaut de page d'un processus multithread par des messages. La seconde est simple et rapide, mais un noyau qui panique emporte tout le groupe.

**Le cas « ouvert » est en fait le cas général.** La l. 436 pose qu'« un service a un thread passif par cœur ». L'espace d'adresses de chaque service est alors actif sur tous les cœurs : chaque service est un processus multithread dont le groupe est la machine entière. Cela contredit le modèle sDDF de pilotes à un seul thread cité l. 46. La phrase « deux cœurs ne s'attendent pas » est fausse dès que le service a un état partagé : le service de stockage n'a qu'un seul écrivain SQLite, et ses threads par cœur se disputeront un verrou en espace utilisateur.

Les applications Wasm n'y échappent pas non plus. Le « parallélisme par plusieurs instances » (l. 684) dans un même processus suppose un runtime multithread, donc le même problème.

**Les capacités sont un état global que le document ne traite pas.** L'arbre de dérivation (l. 747) relie une capacité à ses copies. Dès qu'un service sur le cœur 0 remet un objet à une application sur le cœur 3, l'arbre traverse deux noyaux, et la révocation devient un protocole réparti. La l. 682 ne mentionne la cohérence entre noyaux que pour les processus multithreads. Or la « tâche révocable d'un coup » (l. 686, axe 4), que le document veut revendiquer, est exactement une révocation répartie sur plusieurs cœurs. Barrelfish a eu besoin d'un protocole en deux phases pour cela (de mémoire).

**Recommandation.** Trancher avant l'étape 2 de la piste noyau, par un essai mesuré d'une à deux semaines, sur trois candidats et le même banc (IPC entre cœurs, mappage et révocation dans un processus à huit threads) :

1. messages seulement ;
2. noyau par cœur pour l'état local, verrou court pour l'état d'un processus étalé (l. 698) ;
3. verrou global, comme seL4 en SMP (de mémoire) et Atmosphere (selon la l. 704, non revérifié).

Écrire pour chacun ce qu'il abandonne. Mon avis : la variante 2 est la plus simple qui fasse tourner Ladybird et des services multithreads, et elle renonce à la reprise d'un seul noyau pour la version 1 (voir constat 6). Si cette reprise n'est pas négociable, il faut la variante 1, et prévoir plusieurs semaines pour un protocole de capacités réparti, avec un modèle formel. Retirer dans tous les cas la règle universelle du thread passif par cœur : un service choisit d'être à un thread ou à un thread par cœur.

### 3. L'oracle seL4 ne couvre pas ce noyau ; le modèle exécutable n'est dans aucun contrôle

**Où.** l. 34, 156, 171, 568, 689.

**Statut : confirmé** pour l'absence du modèle dans la liste des contrôles. **Suspecté** pour l'étendue de la couverture.

**Ce que seL4 peut juger.** Les opérations sur les espaces de capacités, les endpoints, les notifications et la création d'objets depuis la mémoire non typée, sur un seul cœur. Le document reconnaît la limite du cœur unique (l. 568) et celle de la surface d'ABI (l. 689).

**Ce qu'il ne peut pas juger.** Tout ce que le document ajoute : un noyau par cœur, les objets mémoire à la Fuchsia avec copie à l'écriture, la pagination en espace utilisateur, l'IOMMU, la tâche comme objet, les étiquettes de provenance. L'ordonnancement non plus : seL4 MCS ordonne par priorité fixe (de mémoire), alors que la l. 424 choisit l'échéance la plus proche. Les décisions d'ordonnancement des deux noyaux ne sont pas comparables.

**Trois trous.**

- L'ABI de DodOS n'est pas celle de seL4 (l. 34). Il faut donc une couche qui traduit chaque suite d'appels vers les deux noyaux. Elle est écrite par des agents, et sa liste de « différences attendues » est l'endroit où une divergence se cache.
- Le workflow impose l'ordre « spécification, modèle, oracle, implémentation » (l. 171), mais la liste « Contrôles par étape » (l. 156) ne dit nulle part que l'implémentation est testée contre le modèle. Rien ne dit qui écrit le modèle, ni que l'agent qui implémente n'a pas le droit de le modifier.
- Si la même famille de modèles écrit le modèle, les tests et le code depuis le même brief, une erreur de compréhension passe les trois.

**Recommandation.**

1. Le modèle exécutable est l'artefact de la voie contrat : relu par les deux humains, protégé par `CODEOWNERS`, écrit par une autre famille de modèles que l'implémentation.
2. À chaque PR, test différentiel de l'implémentation contre le modèle, sur des suites d'appels aléatoires, y compris des entrelacements entre cœurs en simulation. seL4 reste un second oracle, sur le sous-ensemble commun.
3. La liste des différences acceptées avec seL4 devient un fichier protégé, avec un compteur à cliquet.
4. Un modèle vérifié par exploration d'états (TLA+ ou équivalent) pour les trois protocoles répartis : révocation entre cœurs, changement de taille d'un groupe, reprise d'un noyau. La simulation déterministe trouve des bugs ; elle ne remplace pas ce contrôle.
5. Écrire quelles propriétés Verus doit prouver. Le document dit « Verus sur la logique Rust » sans en nommer une.

### 4. Sécurité de l'agent : le modèle ne tient pas avec `core.wit`

**Où.** l. 294, 365, 367, 630, 691 ; `core.wit` l. 11, 110-118, 133-138.

**Statut : confirmé** par lecture de `core.wit` pour les points a, b, c, e et f. **Suspecté** pour d et g.

**a. La parade au mensonge sur la classe d'effet n'est pas réalisable.** La l. 630 affirme qu'une action déclarée `read` « ne reçoit que des capacités en lecture et pas de réseau », donc que mentir ne donne rien. Dans le monde `app`, l'instance reçoit sa collection `home` en lecture et écriture au lancement (`start`, `core.wit` l. 137), garde les droits de son manifeste, et `invoke` s'exécute dans cette même instance. Une action déclarée `read` peut écrire, et envoyer sur le réseau si l'application y a droit. Pour que la parade tienne, il faut exécuter chaque action dans une instance neuve, avec des capacités réduites selon sa classe.

**b. La classe d'effet mélange deux axes.** `enum effect { read, reversible, irreversible, external }` range sur une seule échelle la modification (aucune, réversible, irréversible) et la portée (locale, externe). Une recherche web est une lecture externe : classée `read`, elle laisse sortir des données privées dans la requête ; classée `external`, elle demande une confirmation à chaque recherche.

**c. La règle de confirmation rend l'étiquette inutile.** La l. 365 dit que les classes irréversible et externe demandent toujours une confirmation. La l. 294 dit qu'une tâche marquée « non fiable » voit ses effets externes confirmés. Comme ils le sont déjà toujours, l'étiquette ne change aucune décision. Il manque la matrice (classe d'effet × provenance) → automatique, confirmé ou refusé.

**d. Rien ne dit quelles sorties sont fiables.** L'enregistrement `action` n'a aucun champ sur la confiance à accorder au résultat. Le système doit donc tenir pour non fiable toute sortie d'une application tierce, et toute tâche est marquée dès sa première lecture. Le document liste ce risque (l. 691) sans réponse.

**e. La classe est déclarée à l'exécution.** `list-actions` est une fonction : une application peut changer ses classes après l'installation. Il faut aussi la lancer pour connaître ses actions. La liste et les classes devraient être dans le manifeste signé.

**f. Les secrets passent par le modèle.** `field-kind` a un cas `secret`, et l'événement `changed` remet la valeur de tout champ au propriétaire de la surface, donc à l'agent. Un champ secret ne devrait jamais émettre sa valeur ; elle devrait aller à l'action par `source::input`, sans passer par l'agent.

**g. Ce que montre la confirmation.** L'entrée d'une action est une chaîne JSON opaque. Le compositeur ne peut pas montrer à l'utilisateur ce qui va partir sans interpréter le schéma, et le texte qui l'entoure vient du modèle, donc potentiellement du contenu injecté.

**h. La règle de la l. 367** (« aucun composant ne cumule données privées, contenu non fiable et communication externe ») est violée par construction par le processus de contenu web. Elle reprend sans les citer la « triade létale » de Simon Willison (juin 2025) et la « règle de deux » de Meta (octobre 2025).

**Recommandation.** Écrire la page du modèle de sécurité (que la l. 626 place à l'étape 0) avant de figer `core.wit`. Séparer la classe d'effet en deux champs. Mettre les actions dans le manifeste. Bâtir dans la piste hébergée une suite d'attaques par injection, qui devient une porte : la première démonstration publique est précisément cet agent. Lire FIDES, RTBAS et IsolateGPT en plus de CaMeL : ces travaux étiquettent chaque valeur plutôt que la tâche entière, ce qui réduit le nombre de confirmations.

### 5. Ordre de construction et calendrier

**Où.** l. 84, 87, 105-124, 547, 642-652.

**Statut : confirmé** pour les erreurs d'ordre. **Suspecté** pour les durées, qui sont mon estimation.

**Erreurs d'ordre.**

- *mlibc et la bibliothèque standard de Rust sont placées en « Convergence »* (l. 124), après le triangle Vulkan (l. 122). Or le compilateur de shaders de NVK est écrit en Rust, et Mesa demande une libc et libc++. Les services de stockage et de réseau, natifs en Rust, sont nécessaires à l'image serveur prévue au premier trimestre (l. 648). La l. 84 dit d'ailleurs « obligatoire tôt ». Leur place est à l'étape 2 de la piste noyau.
- *Le pilote NVMe passe par la couche d'émulation* (l. 121), ce qui met cette couche sur le chemin de tout essai sur matériel. Un pilote NVMe natif est petit, et le réservoir d'idées le propose déjà (l. 517).
- *La reprise d'un noyau de cœur* est au premier trimestre 2027 (l. 648), alors qu'elle est « proposée » et dépend du choix multithread encore ouvert.
- *L'image serveur* est « ouverte » l. 547 et jalon l. 648.
- *La pile réseau* est « ouverte, essai prioritaire » (l. 57) et n'apparaît dans aucune étape.
- *L'amorçage de la plate-forme* (UEFI, ACPI, énumération PCI, interruptions, minuteurs, démarrage des autres cœurs) n'apparaît dans aucune étape.

**Ce que le document traite comme facile et qui est sur le chemin critique.**

- Le portage du cœur NVIDIA en processus utilisateur, avec son firmware et sa couche d'affichage. Sans lui, rien ne s'affiche au-delà du framebuffer du firmware, et aucune porte de latence ne se mesure.
- mlibc et la bibliothèque standard de Rust sur la cible.
- Ladybird : l'audit du document lui-même donne 4 à 7 mois à deux (l. 87), le calendrier lui donne un trimestre partagé avec le compositeur réel, l'audio et la veille (l. 649).
- Les contrats du noyau, dont aucun n'est décidé (ordonnancement, mémoire et multi-cœur sont « proposés » ou « ouverts »).

**Ce qui ne se compresse pas avec plus d'agents**, en plus de la liste de la l. 652 :

- *Le nombre de contrats à faire passer par deux humains.* J'en compte une trentaine avant l'alpha : modèle d'objets et appels système, IPC, structure multi-cœur, révocation, ordonnancement, mémoire, IOMMU et interruptions, six interfaces de classe de pilotes plus les bus, format du magasin, format de paquet, mises à jour, modèle de menace, sécurité de l'agent, les interfaces de `os:core`, protocole du compositeur, saisie, accessibilité, service de clés, comptes. À deux ou trois par semaine, c'est dix à quinze semaines de calendrier, quel que soit le nombre d'agents.
- *Une seule machine de référence.* Les essais sur matériel sont en série, et la même machine sert aux portes de latence.

**Calendrier que j'écrirais à la place.** Hypothèses : trois machines de référence identiques et une machine de contrôle ; revue des contrats à deux ou trois fiches par semaine ; semaine 1 le 16 novembre 2026.

| Semaines | Piste hébergée | Piste noyau | Jalon |
|---|---|---|---|
| 1-2 | Étape 0 complète, page du modèle de menace, runtime et `dodo` | Essais qui lèvent les inconnues « de mémoire » : frontière Zig et Rust, noyau sans pile par thread, harnais de l'oracle ; démarrage sous QEMU | Socle prêt, inconnues classées |
| 3-7 (fin 2026) | Surface, actions, agent, confirmations, suite d'attaques par injection | Fiches et modèle du sous-ensemble à un cœur ; capacités, IPC, mémoire de base ; essai comparatif des trois structures multi-cœur | Démonstration : agent hébergé ; noyau à un cœur sous QEMU qui passe le modèle et l'oracle ; IPC à un cœur mesuré sur la machine |
| 8-15 | Shell, magasin réel, paquets signés, pile réseau hébergée | Multi-cœur selon la structure choisie, ordonnancement, mlibc et Rust std, premier service natif, virtio | Composant `wasi:http` servi par le noyau sous QEMU |
| 16-24 | Services portés sur la cible | Amorçage sur le desktop : ACPI, PCI, IOMMU, NVMe natif, clavier ; émulation Linux pour la carte réseau | Image serveur sur le desktop |
| 25-34 | Dépendances de Ladybird sur mlibc | Cœur NVIDIA, NVK, service GPU ; USB, audio | Triangle Vulkan, compositeur sur scanout réel |
| 35-46 | Ladybird, portes de latence calibrées | Durcissement | Alpha sur le desktop (vers octobre 2027) |
| 2028 | Portables, application compagnon, usage quotidien | Reprise d'un noyau de cœur, si elle est retenue | Bêta |

La ligne NVIDIA est la plus incertaine : comptez huit semaines de marge dans un sens ou dans l'autre. Les deux premières lignes du calendrier actuel sont crédibles côté hébergé. Elles ne le sont pas côté noyau au-delà d'un cœur.

## Constats majeurs

### 6. Reprise d'un noyau de cœur : invariants non écrits, valeur faible en version 1

**Où.** l. 207-217. **Statut : suspecté** pour la conception ; **confirmé** pour l'antériorité manquante.

- *La propriété de la mémoire.* Chaque noyau gère sa réserve de pages (l. 463) et les objets mémoire qu'il a créés. Si ces objets sont mappés par des processus d'autres cœurs, le noyau rechargé ne sait pas quelles pages sont encore utilisées. Les réutiliser corrompt la machine. La reprise suppose donc que rien dont dépend un noyau vivant ne soit enregistré seulement dans le noyau mort. Cet invariant n'est écrit nulle part.
- *Les périphériques.* Un pilote qui tournait sur ce cœur laisse un domaine IOMMU actif et un périphérique qui écrit encore en mémoire. Il faut réinitialiser le périphérique avant de reprendre sa mémoire ; l'ordre n'est pas dit.
- *L'hypothèse d'arrêt net.* Valider les messages reçus (l. 208) contrôle leur forme, pas leur vérité. Un noyau qui corrompt ses propres tables de pages peut abîmer le service de stockage avant de paniquer.
- *La valeur.* Dans un micronoyau, la plupart des pannes sont en espace utilisateur et se redémarrent déjà. Avec un démarrage en deux secondes et un état rechargé depuis le stockage, un redémarrage complet coûte à peu près autant, pour les processus touchés, que la reprise d'un cœur.
- *Le remplacement cœur par cœur* fait cohabiter deux versions du noyau qui s'échangent des messages. Le protocole doit alors être compatible d'une version à la suivante ; rien ne le prévoit.
- *Antériorité manquante.* Hive (SOSP 1995) découpe le noyau en cellules pour qu'une panne n'en touche qu'une. Il traite déjà le problème central, les écritures sauvages d'une cellule fautive, par un pare-feu matériel et l'abandon des pages douteuses. C'est le précédent le plus proche, et la l. 217 ne le cite pas.

**Recommandation.** Garder les invariants bon marché (messages validés, aucun mappage partagé entre noyaux). En version 1, une panique écrit sa trace et redémarre la machine. Traiter la reprise d'un cœur comme un axe de recherche après l'alpha, et commencer par écrire l'invariant de propriété de la mémoire.

### 7. Ordonnancement : le budget suit l'appel, mais l'ABI est asynchrone

**Où.** l. 424-456. **Statut : confirmé** pour les contradictions de texte (b, d) ; **suspecté** pour le reste.

- **a.** « Le budget suit l'appel » (l. 425) décrit un appel synchrone : le client attend, le service tourne sur son contexte. La règle 4 de l'ABI fait de l'asynchrone le défaut (l. 352). Un client qui n'attend pas garde son contexte ; rien ne dit sur quel budget le service travaille. La l. 438 esquisse la réponse pour les entrées-sorties (« la requête porte une tranche de son budget ») ; il faut la généraliser et l'écrire.
- **b.** « Un service n'a pas de temps propre » (l. 425) est contredit par le service audio « avec un budget d'ordonnancement garanti » (l. 301), par la réserve de la classe image (l. 427) et par les pilotes qui traitent « sur leur propre contexte » (l. 438). Le stockage a du travail de fond, et la pile réseau reçoit des paquets avant de savoir à qui ils sont.
- **c.** « Un service doit écrire des requêtes annulables » (l. 436, règle 4) est impossible pour un pilote Linux émulé et irréaliste pour du code natif tiers.
- **d.** Le noyau « ne déplace jamais un thread de lui-même » (l. 424), puis un cœur sans travail « demande un contexte prêt à un voisin » par réflexe dans le noyau (l. 450).
- **e.** *Le rafraîchissement de l'écran comme horloge du noyau* (l. 428). Deux écrans à des cadences différentes, une cadence variable, un serveur sans écran (que la l. 553 exige de supporter) : le noyau dépendrait d'un pilote GPU en espace utilisateur pour sa base de temps. La période est déjà un attribut de chaque contexte ; c'est au compositeur d'aligner la sienne sur l'écran.
- **f.** La porte d'IPC (l. 396) mesure le chemin synchrone, que la plupart des appels n'emprunteront pas. Ajouter une porte sur un appel WIT asynchrone entre deux processus, de bout en bout.
- **g.** La référence de la porte décidée est à préciser. Les chiffres cités (environ 740 et 600 cycles) sont ceux de la configuration par défaut de seL4, sans contextes d'ordonnancement et sans atténuation de Meltdown, sur un processeur de 2015. La configuration MCS, comparable à ce noyau, donne 767 et 666. Il faut mesurer seL4 MCS sur la machine de référence.

### 8. Mémoire : quatre modèles superposés, une comptabilité contradictoire

**Où.** l. 458-477, 590. **Statut : confirmé** pour b et f ; **suspecté** pour le reste.

- **a.** « Pas de tas dans le noyau » (l. 462) vient de seL4, où l'espace utilisateur fournit toute la mémoire, y compris les tables de pages. Les réserves de pages par noyau (l. 463) et les pages comptées au premier accès (l. 468) viennent d'un noyau qui alloue lui-même. Au moment d'un défaut de page, qui fournit la page et la table de pages intermédiaire ? Le document ne le dit pas.
- **b.** « Sans surengagement », « comptée au premier accès » et « erreur d'allocation rendue au runtime » (l. 468) ne vont pas ensemble. Si le compte se fait au premier accès, le dépassement arrive pendant un défaut de page, où il n'y a aucune erreur à rendre. Il faut compter à la réservation (`memory.grow`, mappage).
- **c.** Du code natif qui reçoit une erreur d'allocation s'arrête, en général. « Pas de processus tué par surprise » ne vaut que pour le Wasm.
- **d.** Des pages de 2 Mo par défaut pour chaque mémoire Wasm (l. 467) fixent un plancher de 2 Mo par instance. Cela joue contre « plusieurs instances » pour le parallélisme, contre une instance par requête sur un serveur, et contre l'embarqué.
- **e.** Les pages de garde ne retirent les contrôles de bornes que pour des mémoires 32 bits, donc 4 Go au plus par instance. Les mémoires 64 bits demandent des contrôles explicites.
- **f.** « Tuer un processus sans instantané est le dernier recours » (l. 469) contre « on ne tue jamais sans instantané » (l. 590).
- **g.** Le service de stockage pagine le code de tous les processus (l. 465). S'il redémarre, qui pagine le code de celui qui le redémarre ? Les services de l'image de démarrage doivent être épinglés en mémoire, et leur liste (l. 55 : noyau, stockage, pilote disque) omet le gestionnaire de services, le service de mémoire et le service de placement.
- **h.** L'approche de CortenMM (l. 466) suppose un seul noyau qui verrouille finement la table de pages. Dans un modèle à messages, qui écrit la table partagée par un groupe ?

### 9. Stockage : un seul journal SQLite ne suffit pas dès qu'il y a des zones chiffrées

**Où.** l. 50, 203, 206, 221, 223-246, 401, 729. **Statut : confirmé** pour a et d ; **suspecté** pour le reste.

- **a.** Les zones ont des clés différentes : clé du TPM pour l'appareil, clé de chaque utilisateur (l. 234-236). Leurs métadonnées ne peuvent pas vivre dans un seul fichier SQLite chiffré. Avec plusieurs bases en mode WAL, une transaction qui en touche deux n'est pas atomique : la documentation de SQLite le dit explicitement. Or la carte des extents libres est à la machine et la table des objets à l'utilisateur. « Cohérence assurée par le seul journal de SQLite » (l. 50) ne tient donc pas tel quel. Il faut une discipline d'ordre (allouer et valider dans la base de la machine, référencer ensuite, ramasser les fuites) et un test par injection de coupures.
- **b.** La déduplication par contenu ne traverse pas des zones chiffrées par des clés différentes.
- **c.** Les bases SQLite des applications sur des extents en copie à l'écriture, dont la carte est dans la base SQLite du système : un journal sur un journal. Chaque validation d'une application devient une validation du système, et SQLite n'a qu'un écrivain pour toute la machine. La porte « ≥ 90 % du débit NVMe brut » (l. 401) ne tiendra que pour de gros objets séquentiels. Il faut une porte par type de charge.
- **d.** « La racine du stockage bascule de façon atomique » (l. 206) et « dernier instantané, bascule de la racine, coupure » (l. 221) décrivent un autre mécanisme que le journal de SQLite. La seconde phrase suppose un état qui n'est durable qu'à l'arrêt, ce qui contredit « cohérent à tout instant » (l. 203).
- **e.** Le retour arrière A/B (l. 55) partage le magasin entre deux versions du système. Si la nouvelle a migré le schéma, l'ancienne ne le lit plus. Il faut une règle (format compatible avec la version précédente) et son test.
- **f.** Absents : disque plein (SQLite a besoin d'espace même pour supprimer), TRIM, corruption de la base (un seul fichier porte tous les noms, versions et droits ; prévoir des copies et des sommes de contrôle), et un point de durabilité dans l'ABI (voir constat 12).
- **g.** Point levé : SQLite en mode WAL avec un VFS maison (l. 729, « de mémoire ») fonctionne sans mémoire partagée si le verrouillage exclusif est choisi avant le premier accès. Un seul processus peut alors ouvrir la base, ce qui est le cas ici.

### 10. Pilotes Linux : antériorité manquante, licence, et le cas de l'USB

**Où.** l. 45-46, 61, 517, 669. **Statut : confirmé** pour a (SUD, LKL), b et d ; **suspecté** pour c.

- **a.** La l. 45 présente la compilation des sous-systèmes Linux avec le pilote comme ce qui distingue l'approche. C'est vrai face à LinuxKPI. Ce ne l'est pas face à SUD (USENIX ATC 2010), qui fait tourner des pilotes Linux non modifiés en processus utilisateur confinés par l'IOMMU, en s'appuyant sur User-Mode Linux pour l'environnement noyau. Ni face à LKL, qui compile Linux en bibliothèque derrière une petite interface d'hôte. Ni, de mémoire, face à l'approche actuelle de Genode. Ces travaux donnent le coût réel et sont à lire avant d'écrire la couche ; le document classe Genode « de mémoire » (l. 732).
- **b.** *Licence.* La bibliothèque d'émulation est liée à du code GPLv2 seule. Elle doit donc être sous une licence compatible avec la GPLv2, ce que l'AGPLv3 n'est pas. La l. 61 dit seulement « pilotes Linux en GPLv2 dans des processus séparés ». Il faut décider la licence de la bibliothèque et de tout ce qui est lié dans le processus pilote.
- **c.** *Un processus par pilote* ne tient pas pour l'USB : le contrôleur, le cœur USB et les pilotes de classe forment un seul sous-système. La liste des interfaces (l. 46) n'a aucune interface de bus. Sans elle, le clavier, les clés de stockage, le son USB et le transport Bluetooth partagent un processus, alors que le modèle de menace inclut le périphérique branché (l. 626).
- **d.** *Version.* Aucun noyau 7.x n'est désigné à support long sur kernel.org à ce jour. La presse donne 7.3 et 7.4 comme candidats. L'annonce attribuée à Greg Kroah-Hartman (l. 45) n'est pas confirmée par mes recherches.

### 11. Plan de vérification : ce qui laisserait passer du code noyau faux

**Où.** l. 128-191, 392, 634. **Statut** indiqué par point. Ces points s'ajoutent au constat 3.

1. *Le chemin rapide en Zig* n'est couvert ni par Miri, ni par Kani, ni par Verus. Il manipule directement les structures de la logique Rust, puisqu'aucun appel ne traverse la frontière (l. 36). Il y a donc deux implémentations de la même sémantique. Ajouter un test d'équivalence : même corpus, chemin rapide activé puis désactivé, traces identiques. **Suspecté.**
2. *Les échappatoires de Verus* (`assume`, `admit`, corps externes) ne figurent pas dans les budgets à cliquet (l. 145). Une preuve écrite par un agent peut être vide de sens. Les spécifications sont à relire par un humain, pas les preuves. **Confirmé** (absent du texte).
3. *« Comptes de cycles déterministes sous QEMU »* (l. 158) n'existe pas. Avec KVM, rien n'est déterministe. En émulation pure avec compteur d'instructions, on obtient un nombre d'instructions, pas des cycles. C'est un signal de régression utile, à nommer correctement. **Confirmé** (erreur de fait).
4. *Le desktop de référence comme runner* (l. 147) ne peut pas à la fois exécuter le runner GitHub et démarrer DodOS. Il faut une machine de contrôle qui pilote l'alimentation, la console et l'image. Les guides de sécurité déconseillent par ailleurs tout runner auto-hébergé sur un dépôt public. **Confirmé.**
5. *KVM sur les runners gratuits* fonctionne, mais la documentation de GitHub le dit non supporté. Ne pas en faire la seule porte. **Confirmé.**
6. *La simulation déterministe* éprouve le protocole de messages, pas la concurrence réelle des files sans verrou. L'ordre mémoire fort de x86 masque des bugs qui sortiront sur ARM64, que le principe de portabilité (l. 25) vise. Ajouter une exploration systématique des entrelacements sur ces files et des tests de charge sur matériel. **Suspecté.**
7. *Aucun test d'attaque.* Chaque frontière (IOMMU, capacités, pages exécutables, service de compilation) devrait avoir un test qui tente de la franchir et doit échouer. La liste n'a que le fuzzing des appels système. **Confirmé** (absent).
8. *La file de fusion est par dépôt.* Une rupture entre dépôts n'apparaît qu'au déplacement de l'épingle, après la fusion. Soit le déplacement d'épingle est lui-même la porte, soit le noyau, son modèle, l'oracle et `os:core` vivent dans un seul dépôt. Le principe « pas de monorepo » (l. 23) a ici un coût réel. **Suspecté.**
9. *La capacité des humains n'est pas comptée.* Chaque tâche demande des tests écrits ou validés par un humain (l. 179) et une fusion par un humain (l. 183). Au rythme d'une équipe d'agents, deux personnes ne peuvent pas relire réellement chaque tâche, et la relecture cessera d'en être une. Les règles se contredisent en outre : entretien avec « un relecteur » (l. 170), « fusion par un humain » (l. 183), « fusion automatique » (l. 634). **Confirmé.**
10. *Portes « à chaque fusion »* (l. 20, 392) contre portes « la nuit » (l. 146, 158). **Confirmé.**
11. *Test de mutation* la nuit, sans seuil. En faire un cliquet sur la logique du noyau. **Confirmé** (absent).
12. *Les relecteurs ne reçoivent que le diff* (l. 182). Les invariants qui traversent le code leur échappent. Leur donner le dépôt en lecture. **Suspecté.**
13. *Aucun rendu logiciel.* Les captures de référence du compositeur sur la cible demandent la machine NVIDIA. Un pilote virtio-gpu et un rendu logiciel rendraient ces tests possibles sous QEMU. **Suspecté.**

### 12. `core.wit` face au document

**Statut : confirmé** par lecture du fichier, sauf mention.

**Règles du document non reflétées.**

- *Règle 6* (gros volumes par handle ou par flux). `collection.query` rend `list<object>` sans borne. `table` passe ses lignes par valeur. Il n'existe aucun type « handle de tampon ».
- *Règle 5* (identifiants stables). `object.id()` rend une chaîne dont rien ne dit le format ni l'usage.
- *Persistance des droits* (l. 51). Aucune interface pour conserver un objet reçu d'un lancement à l'autre.
- *Provenance* (l. 59, 294). Absente des objets, des résultats d'action et des événements.
- *Icônes* (l. 344) : `icon(string)`. *Annulation, versions, filtre, deux catalogues* : déjà notés l. 681.
- *« Aucun service ne suppose un écran »* (l. 553) : `start` impose un `surface`.
- *Quatre façons de dessiner* (l. 98) : seule la première a une interface. Rien pour WebGPU, les événements d'entrée, la saisie de texte, le presse-papiers.
- *Capacités typées par WIT* (l. 693c). Les actions sont au contraire des chaînes JSON passées à un `invoke` dynamique. Le contrôle des changements cassants de WIT (l. 157) ne voit donc pas un changement de schéma d'action.

**Risques pour l'ABI.**

- *Variants fermés.* Ajouter un cas à un variant ou à un enum casse la compatibilité (confirmé par une discussion publique des mainteneurs). `error` n'a que quatre cas : il manque « introuvable », « existe déjà », quota dépassé, annulé, délai dépassé, refus de l'utilisateur, erreur d'entrée-sortie. Les applications analyseront la chaîne de `invalid(string)`, qui deviendra une ABI de fait. Prévoir une liste large et un cas de repli dès la première version.
- `kind` est l'endroit le plus fragile : le catalogue doit doubler (l. 343), et chaque ajout est une nouvelle version que le système devra servir pour toujours (l. 681). Envisager un encodage ouvert pour l'arbre.
- `event` va du système vers l'application : y ajouter un cas casse les anciens composants.
- Formats de chaîne non spécifiés, qui sont de l'ABI : `invocation.app`, le JSON des arguments, la valeur de `changed`, le filtre de `query`.

**Interfaces manquantes.**

- *Stockage :* point de durabilité (`sync`), troncature, type de contenu, métadonnées, versions avec écriture conditionnelle, notification de changement, liste des noms, sous-collections, quota, `attenuate` sur `collection`, duplication d'un handle, lecture des droits détenus.
- *Actions :* retour d'objets (un export ne peut rien rendre d'autre qu'une chaîne), schéma de sortie, progression, association des objets aux arguments autrement que par position.
- *Monde `app` :* cycle de vie (suspension, reprise, arrêt), aucun import WASI.
- *Monde `agent` :* inférence, mémoire, audio, session, sous-tâches, lecture du journal et de l'étiquette, erreur distincte pour un refus de l'utilisateur.

**Conséquence sur les langages.** `async func`, `stream` et `future` demandent WASI 0.3, que seul Rust atteint aujourd'hui (l. 94). Les adaptateurs 0.2 et 0.1 (l. 32) couvrent les interfaces WASI, pas `os:core`. Tel qu'écrit, le monde `app` n'est implémentable qu'en Rust. Il faut soit une variante de `os:core` pour WASI 0.2, soit le dire.

### 13. GPU : une ligne décidée repose sur un mécanisme non vérifié

**Où.** l. 42, 47, 318, 379, 381, 473, 677, 735. **Statut : confirmé** pour l'écart de statut ; **suspecté** pour le reste.

- Le scanout direct et le curseur sur plan matériel sont « décidés » pour la première version (l. 42, 318). Les plans exposés par le cœur NVIDIA sans sa couche Linux sont « de mémoire » (l. 735). Une décision ferme repose sur un fait non vérifié.
- La préemption de l'inférence (l. 677) et l'éviction de mémoire vidéo (l. 473) sont « à vérifier », alors que deux portes en dépendent (l. 379, 381).
- Les chiffres d'inférence par Vulkan (l. 47) valent pour le pilote propriétaire. Sur NVK, que le système utilisera, l'écart est inconnu. La latence de l'agent, cœur de l'expérience, en dépend.
- Le portage repose sur le fork d'une seule personne (X547), dont le dépôt Haiku n'a pas bougé depuis mai 2026.
- Il n'y a aucun chemin de secours. Si ce portage glisse, rien ne s'affiche.

**Recommandation.** Un essai de deux semaines en tête de piste : compiler le cœur NVIDIA hors de Linux, compter les fonctions d'interface à fournir à partir des raccords de Haiku, vérifier les plans et les priorités de canaux. Mesurer llama.cpp sur NVK sous Linux, ce qui est possible dès aujourd'hui.

### 14. Revendications de nouveauté : antériorité manquée

**Statut : confirmé** pour l'existence des travaux marqués d'une source ; « de mémoire » sinon.

| Revendication | Verdict | Travaux manquants |
|---|---|---|
| Tâche comme objet du noyau, révocable d'un coup (l. 688a) | Combinaison plausible. Sa valeur est dans la révocation répartie, non conçue | Escort sur Scout (OSDI 1999) : comptabilité de bout en bout à travers les domaines de protection. De mémoire : activités de Rialto, banques d'espace d'EROS, `cgroup.kill` |
| Provenance dans l'IPC, confirmation humaine comme seule levée (l. 688b) | Combinaison d'idées connues. AgentKernel (arXiv 2609.29647) occupe déjà le titre | FIDES, RTBAS, IsolateGPT, défense par contrôle de flux (arXiv 2409.19091), règle de deux de Meta |
| Groupes de cœurs dynamiques (l. 688c) | Étroit | Hive (SOSP 1995). De mémoire : K2 pour un noyau par type de cœur, Akaros et Tessellation pour l'annonce du nombre de cœurs au runtime |
| Ordonnancement ancré sur l'écran, « aucun noyau trouvé » (l. 693a) | À adoucir | Redline (OSDI 2008) : échéances, admission, mémoire et disque intégrés pour l'interactivité. ADPF d'Android : durée cible par image |
| Capacités typées par WIT, « ne semble pas publiée » (l. 693c) | Pas nouveau comme idée | Contrats de canaux de Singularity. De mémoire : FIDL de Fuchsia, Cap'n Proto, WASI lui-même |
| Wasm comme seule ABI (l. 700) | La contribution sera la mesure | Singularity : processus scellés, sans génération de code, programmes à manifeste. De mémoire : Midori, Inferno |
| Pilotes Linux sans VM (l. 700) | Voir constat 10 | SUD, LKL, Genode |
| Reprise d'un noyau de cœur (l. 217) | Voir constat 6 | Hive |

La ligne « Emprunts » (l. 743-760) ne cite ni Singularity ni Midori, alors que Midori (capacités, asynchrone partout, code géré seul) est, de mémoire, le précédent le plus proche de la thèse entière, agent mis à part.

### 15. Manques, du plus grave au moins grave

**Statut : confirmé** pour l'absence dans le texte ; le classement est mon jugement.

1. *Donner un objet à une application.* Sans autorité ambiante, l'utilisateur ne peut ouvrir un fichier dans une application que par un sélecteur tenu par le système, le glisser-déposer ou le presse-papiers. Ce n'est qu'une idée du réservoir (l. 530), et `core.wit` n'a rien. Sans cela, le système n'est pas utilisable au quotidien.
2. *Exécution en arrière-plan.* Qui tourne sans surface visible, comment une messagerie reçoit un message, ce que devient un lecteur de musique « figé ».
3. *Service de plate-forme.* Qui possède uACPI (son interpréteur touche toute la machine, il est de confiance), l'énumération PCI, le routage des interruptions.
4. *Rendu logiciel et pilote virtio-gpu*, pour les tests et pour toute machine sans GPU supporté.
5. *Certificats et TLS.* Où se termine TLS pour `wasi:http`, qui livre et met à jour les racines de confiance.
6. *Format du magasin entre versions, disque plein, TRIM* (constat 9).
7. *Mise à jour des applications et clés d'éditeur.* Rotation, compromission, perte d'une clé (l'identité est la clé, l. 54), demande de nouveaux droits à la mise à jour.
8. *Entropie.* Aucun générateur aléatoire n'est mentionné, alors que la disposition aléatoire (l. 475) et les clés en dépendent.
9. *Observabilité.* Journal système, profileur (les compteurs matériels sont une capacité à définir), débogueur du noyau. Tenir des portes de latence sans profileur n'est pas réaliste.
10. *Atténuations Spectre à l'entrée du noyau*, et leur coût sur la porte d'IPC.
11. *Ordonnancement des entrées-sorties.* Les budgets couvrent le processeur, la mémoire et le GPU, pas le disque ni le réseau.
12. *Affichage.* Plusieurs écrans, mise à l'échelle, branchement à chaud.
13. *Liste des applications livrées avec l'alpha.* Sans elle, « alpha » n'a pas de définition.
14. *Caméra.* Aucune interface de classe.

### 16. Wasm comme seule ABI : conséquences non tirées

**Où.** l. 32, 39, 94, 103, 296, 399-400, 465. **Statut : confirmé** pour les chiffres ; **suspecté** pour les conséquences.

- La porte de départ « ≤ 1,5 fois le natif » (l. 399) est plus serrée que la mesure citée (2,41 sans `wide-arithmetic`, confirmé). Comme une porte « ne peut que se resserrer » (l. 392), elle échouerait dès le premier jour. Calibrer avant d'armer le cliquet.
- La cible « ≤ 1,2 » dépend d'un étage « à construire entièrement » (l. 39). Le résultat récent sur wasm2c (0,81 à 0,89 fois le temps des meilleurs runtimes) appuie la piste de la l. 414.
- Le surcoût de 3,5 fois sur les appels synchrones entre composants, dû à l'asynchrone, est confirmé. Il touche chaque appel à travers `os:core`.
- Un composant ne peut pas mapper un blob dans sa mémoire linéaire. Chaque lecture est une copie, flux compris. Le « cache de pages partagé » (l. 465) ne sert donc qu'au code et aux services natifs.
- La promesse « un composant publié continue de tourner » (l. 103) est adossée à un standard en version 0.3, qu'un seul langage sait produire.

## Constats modérés

### 17. Contradictions et lignes périmées

**Statut : confirmé.**

| Lignes | Contradiction |
|---|---|
| 96 et 620 | « nushell ne compile pas pour WASI » (vérifié le 13 novembre), puis Nushell candidat pour le shell |
| 469 et 590 | Tuer un processus sans instantané : « dernier recours », puis « jamais » |
| 84 et 124 | Rust std « obligatoire tôt », puis en « Convergence » |
| 424 et 450 | Le noyau ne déplace jamais un thread, puis vol de travail par réflexe dans le noyau |
| 172 et 635 | Fiches de décision dans chaque dépôt, puis dans un dépôt commun |
| 170, 183 et 634 | Entretien : un relecteur, fusion par un humain, fusion automatique |
| 20, 392, 146 et 158 | Portes à chaque fusion, puis la nuit |
| 547 et 648 | Image serveur « ouverte », puis jalon du calendrier |
| 50 et 206 | Journal de SQLite, puis bascule atomique d'une racine |
| 3-4 | Trois statuts définis ; le texte en utilise sept (proposé, en discussion, retenu, accord à concevoir) |
| 396, 305, 342, 344, 560 | Des « décidé » isolés dans des sections titrées « proposé » ou sans statut |
| 24 | Renvoi à une section « Axes de recherche du noyau » qui est une puce des questions ouvertes (l. 686) |

**Recommandation.** Une seule colonne de statut, quatre valeurs définies en tête, et une passe pour retirer les lignes remplacées.

### 18. Faits : ce qui est faux, trompeur ou non confirmé

**Faux ou trompeur (confirmé).**

- l. 158 : les « comptes de cycles déterministes sous QEMU » (constat 11).
- l. 630 : « mentir sur la classe ne donne rien de plus » (constat 4).
- l. 217 et 698 : « retrait en 0,0008 ms contre 2 542 ms pour Linux 3.13 ». D'après le texte extrait des diapositives des auteurs, dont la mise en page est brouillée, Linux y figure à 46 ms sans charge et 2 542 ms sous charge. Le document comparerait donc au pire cas de Linux. Je n'ai pas pu lire le tableau de l'article lui-même : à relire avant de citer ce chiffre.
- l. 45 : la distinction revendiquée face à LinuxKPI ne vaut pas face à SUD et LKL (constat 10).
- l. 147 : le desktop de référence ne peut pas être le runner (constat 11).

**Non confirmé par mes recherches.**

- l. 45 : l'annonce de Linux 7.3 comme noyau à support long de 2026.
- l. 46 : « 1 Gb/s saturé à 65 % d'un cœur, là où Linux plafonne à 500 Mb/s ». Je n'ai trouvé que des graphiques, sans ces valeurs.
- l. 47 : « moins de la moitié » pour NVK sur RTX 5080. Le sens est confirmé (écart important), le chiffre non.
- l. 704 : 6 000 lignes, 2,5 années-personne et verrou global pour Atmosphere. Seul le rapport preuve sur code de 3,32 est confirmé.
- l. 682 : seL4 « déconseille l'IPC entre cœurs » dans son multinoyau.
- l. 44 : la version 1.0 d'A2UI existe dans le dépôt ; le « format Express » n'a pas été vérifié.

**À préciser.** Zig est en version 0.17.1, donc sans engagement de stabilité, ce qui pèse sur le principe « fait pour durer » (l. 25) sans contredire la décision. Ladybird n'a publié aucune version : « on suit les versions publiées » (l. 41) n'a encore rien à suivre.

### 19. Périmètre : à couper, à reporter, sous-estimé

**Statut : suspecté** (jugement).

**À reporter après l'alpha.**

- Reprise d'un noyau de cœur et remplacement du noyau à chaud.
- Instantané périodique de tous les processus.
- Étage optimisé de compilation Wasm, et la porte à 1,2.
- Communication entre appareils et application compagnon sur cinq systèmes. Sur iOS, sans droit de générer du code, le Wasm devra être interprété.
- Fréquence à la demande, cœurs à la demande, noyau spécialisé par machine ou par type de cœur.
- Mise à l'échelle et génération d'images (l. 672).

**À simplifier.**

- Trois moteurs de rendu au « rendu identique » (l. 343) : deux en version 1.
- Second type d'objet, versions fines et quotas en même temps : commencer par un fichier d'extents simple pour les bases.
- Un dépôt par composant : en regrouper plusieurs (constat 11, point 8).

**Sous-estimé.**

- Le modèle de sécurité de l'agent.
- Le don d'objet par le geste.
- L'amorçage de la plate-forme.
- Le portage NVIDIA.
- L'infrastructure de test : trois machines et une machine de contrôle.
- Le modèle exécutable du noyau.
- L'entretien d'un fork perpétuel de navigateur, correctifs de sécurité compris.

### 20. Communication entre appareils

**Où.** l. 479-487. **Statut : suspecté.**

Le principe « un appareil n'est qu'un détenteur de capacités de plus » est celui des capacités réparties (CapTP du langage E, Cap'n Proto ; de mémoire), plus que celui de Plan 9, qui n'a pas de capacités. Ces travaux traitent les points que la section laisse ouverts : ramasse-miettes des références distantes, partition du réseau, révocation. « Un seul agent et une seule mémoire sur tous les appareils » suppose une règle de fusion pour une mémoire tenue dans SQLite. Elle est « à étudier » (l. 487), alors que tout le reste en dépend.

## Constats mineurs

**Statut : suspecté**, sauf mention.

21. *Budgets en temps et fréquence variable* (l. 451). Un budget en millisecondes ne vaut pas le même travail à deux fréquences. Il faut compter en travail, ou renoncer à piloter la fréquence par le budget.
22. *Deux fils d'un même cœur physique* (l. 455). Avec un noyau par fil, les deux noyaux doivent se coordonner à chaque changement de contexte. À décider : un noyau par cœur physique ou par fil.
23. *FRED* (l. 694). Les sources trouvées le donnent sur Panther Lake, des processeurs mobiles. Le desktop de référence ne l'a probablement pas ; le chemin par IDT sera le chemin réel.
24. *Opérations longues dans un noyau sans pile par thread.* La révocation d'un grand sous-arbre ou la mise à zéro d'une page de 2 Mo ne se préemptent pas sans points de reprise. Il faut une borne de durée par appel système, vérifiée.
25. *Bascule A/B sur FAT32* (l. 227). FAT n'a pas de renommage atomique. Le mécanisme de bascule est à écrire.
26. *Console série* (l. 159). Un desktop récent n'en a pas par défaut : prévoir une carte ou le port de débogage USB.
27. *Appels système « jamais en direct »* (l. 37). Rien ne dit comment c'est imposé au code natif. Zircon vérifie que l'appel vient de la page fournie par le noyau (de mémoire).

## Ce qui a été vérifié et jugé solide

**Faits confirmés auprès d'une source primaire.**

- *seL4.* 742 et 597 cycles sur Skylake en configuration par défaut. La RFC-14 existe et propose bien des seuils de budget sur les endpoints (état de fusion inconnu). La preuve du multinoyau est annoncée pour le troisième trimestre 2028.
- *Wasm.* WASI 0.3.0 publié le 11 juin 2026. `wasm32-wasip3` de niveau 2 dans la documentation de Rust 1.100. Wasmtime 46 du 22 juin 2026. Banc libsodium : 2,41 et 1,46 pour Wasmtime, 2,08 et 1,33 pour Wasmer. Surcoût asynchrone de 3,5 fois. `wasi:webgpu` en phase 2. Un cas ajouté à un variant casse la compatibilité.
- *Ladybird.* Fin des contributions externes le 5 juin 2026. Commit `c8b525e` du 13 novembre 2026. PR 14109 (processus Hub), 12492 et 12613 (JIT par défaut), 9156 (lecteurs d'écran). Les services `Compositor` et `Hub` existent.
- *GPU et interface.* Dossiers `src/` et `kernel-open` des modules NVIDIA. Branche `mesa-nvk-r2` de X547/mesa et dépôt `nvidia-haiku`. gpui 0.2.2 sous Apache-2.0 sur crates.io, rendu wgpu sur Linux depuis le 13 février 2026, mode sans écran.
- *Système.* uACPI 7.0.0 (MIT, 16 octobre 2026). sDDF 0.7.0. llama.cpp 1.0.0 du 13 novembre 2026. iroh 1.0.0 du 15 juin 2026. Crate `netstack3-core` 0.1.0 du compte `synaptic-void`, dont le dépôt déclaré rend bien une erreur 404. Linux 7.3 sorti le 18 octobre 2026. RFC-0225 de Fuchsia.
- *Recherche.* CortenMM (1,2 à 26 fois). Otherworld (plus de 97 %). Existence d'AgentKernel, d'ActPlane, de « Fork, Explore, Commit », de l'étude sur `AGENTS.md`. Atelier AgenticOS en mars 2026 puis à SOSP 2026, et Agate à son programme. Réécriture de Bun (8 juillet 2026).

**Conceptions jugées saines.**

- Un service de compilation seul producteur de code machine, avec un cache par hash.
- Un processus par éditeur comme frontière de sécurité, qui borne aussi l'effet d'un bug du compilateur.
- Les blobs immuables vérifiés à la lecture, et le système désigné par un hash.
- L'IOMMU par pilote, avec des mappages durables et le remappage des interruptions.
- L'userland hébergé comme SDK et comme moyen de développer sans attendre le noyau.
- Le harnais des agents dans son principe : commande unique, dossiers protégés, budgets à cliquet, test d'injection de faute pour chaque contrôle, porte anti-triche.
- La séparation entre mécanisme dans le noyau et politique en espace utilisateur pour l'ordonnancement et la mémoire.
- Le constat honnête de la l. 686 : les mécanismes sont empruntés, aucun axe n'est encore conçu.

**Non couvert par cette revue.** Le design system, l'accessibilité, la saisie et l'audio n'ont reçu qu'une lecture de cohérence. Je n'ai lu aucun des articles de recherche en entier, sauf leurs résumés.

## Sources

**seL4 et micronoyaux**

- [seL4 : performance](https://sel4.systems/performance.html)
- [seL4 : feuille de route](https://sel4.systems/roadmap.html)
- [seL4 : liste des RFC, août 2023](https://lists.sel4.systems/hyperkitty/list/rfc@sel4.systems/2023/8/)
- [Johnston, limites de budget d'IPC pour seL4 MCS](https://trustworthy.systems/publications/theses_public/22/Johnston:be.abstract)
- [Barrelfish/DC, article](https://barrelfish.org/publications/zellweger-decoupling-cores.pdf) et [diapositives OSDI 2014](https://usenix.org/sites/default/files/conference/protected-files/osdi14_slides_zellweger.pdf)
- [Hive, SOSP 1995](https://pdos.csail.mit.edu/archive/6.824-2004/papers/hive.pdf)
- [Otherworld, EuroSys 2010](https://www.eecg.utoronto.ca/~stumm/Papers/Depoutovitch-EuroSys10.pdf)
- [Atmosphere, SOSP 2025](https://mars-research.github.io/doc/2025-sosp-atmo.pdf)
- [CortenMM, SOSP 2025](https://zhou-diyu.github.io/files/cortenmm-sosp25.pdf)
- [Redline, OSDI 2008](https://www.usenix.org/conference/osdi-08/redline-first-class-support-interactivity-commodity-operating-systems)
- [Escort sur Scout, OSDI 1999](https://www.usenix.org/conference/osdi-99/defending-against-denial-service-attacks-scout)
- [Singularity : Rethinking the Software Stack](https://www.microsoft.com/en-us/research/publication/singularity-rethinking-the-software-stack/)
- [Android : Performance Hint API](https://developer.android.com/games/optimize/adpf/performance-hint-api)

**Pilotes et Linux**

- [SUD, USENIX ATC 2010](https://www.usenix.org/conference/usenix-atc-10/tolerating-malicious-device-drivers-linux)
- [Linux Kernel Library, RFC de 2015](https://lkml.iu.edu/hypermail/linux/kernel/1511.0/01898.html)
- [Genode : portage de pilotes](https://genode.org/documentation/developer-resources/porting_device_drivers)
- [kernel.org : versions](https://www.kernel.org/category/releases.html)
- [Phoronix : Linux 7.3 publié](https://phoronix.com/news/Linux-7.3-Released)
- [GNU : liste des licences et compatibilité](https://www.gnu.org/licenses/license-list.html)
- [sDDF, versions](https://github.com/au-ts/sddf/releases)
- [uACPI, versions](https://github.com/uACPI/uACPI/releases)

**Wasm**

- [WASI : versions](https://wasi.dev/releases)
- [Bytecode Alliance : WASI 0.3](https://bytecodealliance.org/articles/WASI-0.3)
- [Bytecode Alliance : vers Component Model 1.0](https://bytecodealliance.org/articles/the-road-to-component-model-1-0)
- [Rust : cible wasm32-wasip3](https://doc.rust-lang.org/stable/rustc/platform-support/wasm32-wasip3.html)
- [Performance des runtimes WebAssembly en 2026](https://00f.net/2026/06/23/webassembly-runtimes-2026/)
- [Compilation de WebAssembly vers C en 2026](https://00f.net/2026/07/08/webassembly-compilation-to-c-2026/)
- [WASI : état des propositions](https://github.com/WebAssembly/WASI/blob/main/docs/Proposals.md)
- [Discussion sur la compatibilité des variants](https://bytecodealliance.github.io/zulip-archive/stream/327223-wit-bindgen/topic/Compatibility.20of.20enum.2Fvariant.html)
- [Wasmtime : réglages et pages de garde](https://docs.wasmtime.dev/examples-fast-execution.html)

**Stockage**

- [SQLite : ATTACH DATABASE](https://sqlite.org/lang_attach.html)
- [SQLite : exigences du mode WAL](https://www2.sqlite.org/matrix/matrix_dwal.html)
- [Fuchsia RFC-0225 : Fxblob](https://fuchsia.dev/fuchsia-src/contribute/governance/rfcs/0225_fxblob)

**Ladybird, GPU, interface**

- [Ladybird, dépôt](https://github.com/LadybirdBrowser/ladybird), PR [14109](https://github.com/LadybirdBrowser/ladybird/pull/14109), [12492](https://github.com/LadybirdBrowser/ladybird/pull/12492), [12613](https://github.com/LadybirdBrowser/ladybird/pull/12613), [9156](https://github.com/LadybirdBrowser/ladybird/pull/9156)
- [Linuxiac : Ladybird ferme les PR publiques](https://linuxiac.com/ladybird-browser-closes-public-pull-requests-ahead-of-first-alpha/)
- [NVIDIA : modules ouverts](https://github.com/NVIDIA/open-gpu-kernel-modules)
- [X547 : fork de Mesa](https://github.com/X547/mesa) et [nvidia-haiku](https://github.com/X547/nvidia-haiku)
- [Phoronix : NAK fusionné dans Mesa 24.0](https://www.phoronix.com/news/NAK-Merged-Mesa-24.0)
- [Phoronix : performance de NVK avec Mesa 26.2](https://phoronix.com/news/NVK-Mesa-26.2-Performance)
- [gpui sur crates.io](https://crates.io/crates/gpui) et [PR 46758 de Zed](https://github.com/zed-industries/zed/pull/46758)
- [A2UI, dépôt](https://github.com/google/A2UI)
- [Mesure de FRED sur Panther Lake](https://www.hwcooling.net/en/performance-boost-for-intel-cpus-impact-of-fred-measured/)

**Agents et sécurité**

- [AgentKernel, arXiv 2609.29647](https://arxiv.org/abs/2609.29647)
- [ActPlane, arXiv 2606.25189](https://arxiv.org/abs/2606.25189)
- [Fork, Explore, Commit, arXiv 2602.08199](https://arxiv.org/abs/2602.08199)
- [Évaluation d'AGENTS.md, arXiv 2602.11988](https://arxiv.org/abs/2602.11988)
- [CaMeL, arXiv 2503.18813](https://arxiv.org/abs/2503.18813)
- [FIDES, arXiv 2505.23643](https://arxiv.org/abs/2505.23643)
- [RTBAS, arXiv 2502.08966](https://arxiv.org/abs/2502.08966)
- [IsolateGPT, arXiv 2403.04960](https://arxiv.org/abs/2403.04960)
- [Défense par contrôle de flux d'information, arXiv 2409.19091](https://arxiv.org/abs/2409.19091)
- [Atelier AgenticOS](https://os-for-agent.github.io/)
- [Simon Willison : la triade létale](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- [Simon Willison : règle de deux de Meta](https://simonwillison.net/2025/Nov/2/new-prompt-injection-papers/)

**Outils et infrastructure**

- [GitHub : runners hébergés](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [OWASP : sécurité de GitHub Actions](https://cheatsheetseries.owasp.org/cheatsheets/GitHub_Actions_Security_Cheat_Sheet.html)
- [Zig : téléchargements](https://ziglang.org/download/)
- [llama.cpp 1.0.0](https://github.com/ggml-org/llama.cpp/releases/tag/v1.0.0)
- [iroh 1.0.0](https://github.com/n0-computer/iroh/releases/tag/v1.0.0)
- [Crate netstack3-core](https://crates.io/crates/netstack3-core)
- [Bun : réécriture en Rust](https://bun.com/blog/bun-in-rust.md)
