# DodOS : direction du projet

État au 14 novembre 2026. Issu d'un brainstorming : seules les lignes marquées **Décidé** sont fermes.
Les lignes **Aligné** sont des propositions discutées sans objection. Les lignes **Ouvert** restent à trancher.

## Thèse

Un OS où un agent peut agir en sécurité pour l'utilisateur, et qui ne se met jamais en travers.

Trois raisons d'exister :

1. Les noyaux monolithiques s'érodent sous le nombre de failles. Un micronoyau à capacités est la réponse structurelle.
2. Sortir de l'écosystème Unix / POSIX / glibc / systemd sans enfermer à son tour : l'ABI applicative est un standard (Wasm, WASI, web) qui tourne aussi ailleurs.
3. Une expérience nouvelle : un agent omniprésent, discret et sûr (l'inspiration est Jarvis), dans un shell conçu pour lui, où le web est une surface comme les autres.

## Principes

- Ne pas réinventer la roue : on porte, on emprunte, on n'écrit que ce qui différencie.
- Les tests sont la spécification. C'est ce qui rend fiable du code écrit à deux avec des agents IA.
- La latence est un contrat, vérifié à chaque fusion.
- Aucune autorité ambiante : un programme n'a que ce qu'on lui passe.
- L'utilisateur possède sa machine et ses données.
- Pas de monorepo : un dépôt par composant.
- Le noyau est la pièce maîtresse, celle qui se vend. On part de l'existant pour aller vite, mais le but est d'y apporter du nouveau (voir « Axes de recherche du noyau »), puis dans l'OS lui-même.
- **Portable et fait pour durer** (décidé, 14 novembre 2026) : tout le système, de la dernière application au noyau, est conçu pour être porté et survivre dans le temps. Le support de plusieurs architectures en fait partie : rien ne suppose x86-64 hors de la couche d'architecture.
- **Anglais pour le développement** (décidé, 14 novembre 2026) : code, commentaires, commits, `AGENTS.md`, fiches de décision, documentation des dépôts. Ce document reste en français tant qu'il sert à la discussion ; il sera traduit en entrant dans un dépôt de développement.

## Décisions

| Domaine | Choix | Statut |
|---|---|---|
| ABI applicative | Wasm uniquement, via le Component Model, WIT et WASI 0.3. WASI 0.2 et 0.1 acceptés par adaptateurs, pour élargir les langages | Décidé |
| Noyau | Micronoyau à capacités, 64 bits uniquement, écrit depuis le modèle et non traduit de seL4 | Décidé |
| ABI seL4 | Aucune dépendance durable. seL4 sert seulement d'oracle en boîte noire pour les tests différentiels | Décidé |
| Langages | Noyau en Zig et Rust : Zig pour la couche matérielle et le chemin rapide d'IPC, Rust pour la logique (capacités, cycle de vie des objets, politique d'ordonnancement). Rust pour l'userland système. Odin écarté | Décidé |
| Frontière Zig / Rust | Types définis une fois en Rust `repr(C)`, en-tête C généré, importé par Zig. Aucun appel à travers la frontière sur le chemin rapide. `zig build` pilote cargo et fait l'édition de liens | Aligné |
| Stabilité des ABI | Mondes WIT versionnés et stables, pour les applications comme pour les services et les pilotes. Appels système derrière une page de code fournie par le noyau, jamais appelés en direct | Décidé |
| Structure SMP | Un noyau par cœur, noyau événementiel sans pile par thread (permet le remplacement à chaud). Traitement des processus multithreads ouvert : journal répliqué ou noyau par groupe de cœurs, dynamique (voir Questions ouvertes) | Aligné, multithread ouvert |
| Compilation Wasm | Trois étages, à la ART, avec bascule entre deux lancements par notre service de compilation (Wasmtime ne bascule pas seul). Lancer sans installer : compilateur de base Winch, quasi instantané. Installation : Cranelift, à l'avance. Arrière-plan : étage optimisé, à construire entièrement : aucun backend LLVM ne gère les composants, aucun outil n'abaisse un composant en modules simples, et Cranelift n'a pas d'optimisation guidée par profil. Pas de JIT dans les applications. Surcoût mesuré sur libsodium en 2026 : 2,41 fois le natif pour Wasmtime, 1,46 avec `wide-arithmetic` (voir Portes de surcoût). Fusion des composants d'un même éditeur : outil `meld`, jeune ; composition par `wac` | Aligné, étage optimisé ouvert |
| GPU pour les applications | WebGPU est la seule API GPU exposée aux composants, par `wasi:webgpu`. Implémentation par wgpu (Rust), dans un service GPU séparé du compositeur : gpui et Rune reposent déjà sur wgpu, donc une seule pile à porter. Dawn écarté sauf besoin de son protocole client-serveur. `wgpu-native` n'implémente pas encore l'en-tête `webgpu.h` stable : on passe par l'API Rust. Pipelines mis en cache par hash. WebGPU reste à ajouter à LibWeb | Aligné |
| Moteur web | Fork de Ladybird (LibWeb, LibJS). Fork perpétuel : Ladybird refuse toute contribution externe depuis le 5 juin 2026 et a fermé la demande d'embarquement. On suit les versions publiées, à partir de la première alpha, et on décide de chaque montée de version | Décidé |
| Compositeur | Un petit compositeur système en Rust, écrit par nous, qui assemble des tampons finis. Le Compositor de Ladybird, le shell et le service GPU en sont des clients. Dès la première version : tampons partagés sans copie, scanout direct d'une surface plein écran (aucune composition, aucune image ajoutée), et rappel d'image avec échéance pour que le contenu d'un client parte au même rafraîchissement. Étape intermédiaire : un tampon vidéo séparé, posé sur un plan matériel. Ensuite, un protocole où Ladybird remet plusieurs calques, pour les animations de calques web | Décidé |
| Shell | Pas d'environnement de bureau : un gestionnaire de surfaces centré sur l'agent, qui sert de lanceur. Shell et catalogue DodOS dessinés par gpui (Apache-2.0, publié sur crates.io, rendu wgpu sur Linux depuis février 2026, AccessKit, cible Wasm, mode sans écran), avec les composants de gpui-kit. Rune en recours : pré-version qui refuse toute PR. LibWeb comparé dans le même essai. Mêmes jetons de thème que le web | Aligné, essai à faire |
| Interface de l'agent | Le modèle émet de l'A2UI 1.0 (format Express) contre un catalogue DodOS, traduit vers les types de `core.wit` : liste plate de nœuds, une quinzaine de types, aucun style, aucune URL, aucun code. Boutons liés aux actions typées de la tâche. Applet JS sans capacité pour le reste, dont la 3D | Aligné |
| Pilotes | Pilotes d'un noyau Linux à support long, pris sur kernel.org sans passer par une distribution (version fixée au démarrage de la couche d'émulation ; candidat : Linux 7.3, que Greg Kroah-Hartman a annoncé vouloir désigner LTS de 2026), compilés depuis leurs sources contre une bibliothèque qui réimplémente l'API interne du noyau, un processus par pilote. Ni machine virtuelle, ni noyau Linux, ni traduction d'appels système. Les sous-systèmes Linux dont un pilote dépend (son, Wi-Fi, DRM) sont compilés avec lui, sans les réécrire : c'est ce qui distingue cette approche de LinuxKPI, dont la réécriture à la main est le point douloureux chez FreeBSD. Le pilote NVIDIA ne passe pas par cette couche | Décidé |
| Cadre de pilotes | Une interface stable par classe de périphérique (bloc, réseau, entrée, audio, affichage, GPU). Contrôle en WIT, données par files en mémoire partagée. Un gestionnaire de pilotes associe périphériques et pilotes par règles déclaratives. Un pilote Linux émulé et un pilote natif implémentent la même interface. Le noyau programme l'IOMMU par pilote : sans elle, un pilote peut écrire partout en mémoire par DMA et l'isolation ne vaut rien. Modèles : DFv2 de Fuchsia et sDDF de seL4 (version 0.7.0 : files à un producteur et un consommateur en mémoire partagée, pilotes à un seul thread, virtualiseurs explicites pour partager un périphérique). Mesure publiée par sDDF : un lien 1 Gb/s saturé à 65 % d'un cœur, là où Linux plafonne à 500 Mb/s | Aligné |
| GPU | NVIDIA : cœur indépendant de l'OS des modules ouverts (dossier `src/`), adapté par nos propres raccords, sans la couche Linux `kernel-open`. Vulkan par NVK, à partir du fork de Mesa du portage Haiku (X547/mesa, branche `mesa-nvk-r2`), puisque NVK officiel ne parle qu'à nouveau. Performance de NVK : moins de la moitié du pilote propriétaire en moyenne sur RTX 5080 (Phoronix, mars 2026), environ 70 % constaté par nous sur une carte plus ancienne (CS2 en 1440p), en progrès rapide. Pour l'inférence, Vulkan est derrière CUDA d'environ 10 % en génération et 36 % en lecture du prompt, sur pilote propriétaire. Firmware GSP propriétaire requis. Calcul par Vulkan | Décidé, mécanisme vérifié le 13 novembre 2026 |
| Applications natives | Écartées pour l'instant : Wasm et WIT restent la seule ABI des applications. Une ABI native coûterait plus qu'elle ne rapporte (un binaire par architecture, libc et format d'exécutable à tenir stables, portage de chaque runtime). À rouvrir seulement devant un besoin concret | Aligné |
| Machines virtuelles | Hors périmètre pour faire tourner quoi que ce soit sur l'OS. Les pilotes Linux en micro-VM sont une alternative connue et non retenue (voir Pilotes en micro-VM) | Décidé |
| Stockage | Écrit par nous sur le modèle de blobfs, sans système de fichiers POSIX. SQLite pour les métadonnées (index des blobs, carte des extents libres, objets, versions, droits, mémoire de l'agent), blobs immuables vérifiés par arbre de Merkle pour les données. Un objet modifiable est une suite de blobs référencée par SQLite, les petits objets sont stockés dans SQLite. Cohérence après coupure assurée par le seul journal de SQLite. Clés USB (FAT, exFAT) par un pilote à part, plus tard | Aligné |
| Persistance des droits | Statiques re-dérivés du manifeste, dynamiques dans une table de handles tenue par le système | Aligné |
| Web et capacités | Chaque site est un principal, avec un « monde web » fixe | Aligné |
| Permissions | Centralisées : un droit = une capacité = une ligne révocable | Décidé |
| Distribution | Un paquet est un ensemble de blobs et un manifeste signé. Identité = clé d'éditeur + nom. Lancer sans installer. Magasin central plus tard, jamais obligatoire. Transport à explorer : un registre de conteneurs standard, déjà la voie préférée de la Bytecode Alliance pour distribuer des composants (outil `wkg`) | Décidé, transport ouvert |
| Mises à jour | Le système est un hash. Emplacements A/B/R, retour arrière automatique, métadonnées TUF. Image de démarrage signée (noyau, service de stockage, pilote disque) sur la partition de démarrage | Aligné |
| Sécurité | Service de clés isolé à interface étroite. Classes de protection des données. Indicateurs (microphone, caméra, capture) et confirmations dessinés par le compositeur, hors de portée des applications. Détail proposé dans la section Sécurité, isolation et modularité | Aligné |
| Réseau | Pile en espace utilisateur, `wasi:http` et `wasi:sockets` adossés à des capacités. Netstack3 en premier, par notre propre extraction depuis l'arbre Fuchsia. La crate `netstack3-core` 0.1.0 prouve que c'est faisable, mais elle vient d'un compte anonyme (`synaptic-void`) et son dépôt source est introuvable : à ne pas utiliser telle quelle. Repli : pile NetBSD (rump). smoltcp, lwIP et pile Linux écartés | Ouvert, essai prioritaire |
| Agent | Détection de voix toujours active, le reste à la demande. Modèles interchangeables, local ou cloud. Inférence locale par llama.cpp (1.0 stable depuis le 13 novembre 2026), backend Vulkan | Aligné |
| Mémoire de l'agent | Objets du stockage appartenant à l'utilisateur, avec provenance | Aligné |
| Jeux | Wasm et cloud uniquement | Décidé |
| Licence | Double licence : AGPLv3 et commerciale. SDK et bibliothèques liées aux applications sous licence permissive. Pilotes Linux en GPLv2 dans des processus séparés | Décidé |

## Architecture

```
Agent, shell, applications        composants Wasm, web
---------------------------------------------------------
Mondes WIT (os:core)              la seule ABI visible
---------------------------------------------------------
Services système (Rust)           compositeur, service GPU, moteur web, stockage,
                                  réseau, audio, droits, clés, inférence
Pilotes                           émulation de l'API Linux, cœur NVIDIA
---------------------------------------------------------
Micronoyau (Zig, Rust)            capacités, IPC, ordonnancement, mémoire, IOMMU
```

Les applications, les services et les pilotes ne voient que des mondes WIT stables. Seuls les appels système bruts sont privés, derrière la page de code fournie par le noyau.

## Comment l'userland compile contre l'OS

- **Composants Wasm** (applications, agent) : cible Wasm standard, aucune chaîne d'outils propre à l'OS.
- **Code natif Rust** : une cible `x86_64-unknown-dodos`, et une crate de plateforme à deux implémentations, hébergée (Linux, macOS) et native. Les services s'écrivent contre elle et compilent pour les deux.
- **Code natif C et C++** (moteur web, Skia, Mesa, SQLite, pilotes) : mlibc avec notre couche système, libc++, compilation croisée par clang ou `zig cc`.
- **Bibliothèque standard de Rust sur notre cible** : obligatoire tôt. Voie la plus courte : la brancher sur mlibc, qu'on porte de toute façon. Le support Rust de seL4 sert de modèle pour la crate de plateforme sans bibliothèque standard. Ladybird compte une trentaine de crates Rust (LibJS, son JIT, le moteur CSS, le cœur du Compositor, LibWasm).
- **POSIX en bibliothèque** : un descripteur de fichier est un handle, et chaque processus reçoit de son parent une table de noms. Pas de système de fichiers global.
- **Édition de liens statique** d'abord. Le chargement des exécutables se fait en espace utilisateur.
- **Portage de Ladybird** (vérifié sur le commit c8b525e du 13 novembre 2026) : LibCore (variantes POSIX et Windows, macOS réutilise POSIX), un transport LibIPC (socket Unix, Windows avec courtier de handles, port Mach), 49 dépendances vcpkg sur mlibc, les crates Rust, et aussi un backend AudioServer, le bac à sable, les polices sans Fontconfig, RequestServer (curl) sur notre pile réseau. Le processus Hub, sans Qt depuis la PR 14109, est la jointure de contrôle. Estimation de l'audit : 4 à 7 mois à deux une fois mlibc, Rust, Vulkan et le réseau en place.

## Parcours développeur

Le SDK est l'userland hébergé : un développeur n'a besoin ni de DodOS ni d'une machine virtuelle.

- **Un outil, `dodo`** : `new`, `run` (lance le composant sur Linux ou macOS dans une fenêtre), `test`, `actions` (appelle les actions exportées comme le ferait l'agent), `package` (blobs et manifeste signé). `dodo run <url>` lance sans installer.
- **Langages**, état vérifié le 13 novembre 2026. Composants WASI 0.3 : Rust seul (cible `wasm32-wasip3` de niveau 2 depuis Rust 1.100). Composants WASI 0.2 : C et C++ (wasi-sdk), Go et TinyGo, Python (`componentize-py`), JS (`ComponentizeJS`, ou `componentize-qjs` plus léger), C# en pré-version. Modules WASI 0.1 seulement, à envelopper par l'adaptateur standard : Zig, Swift, Ruby. Sans chemin aujourd'hui : Kotlin, Java et Dart (WasmGC n'est pas encore compatible avec l'asynchrone des composants dans Wasmtime), PHP, Lua, Elixir. Odin non vérifié. JS et TS des applications web tournent sur LibJS. Limites de Wasm : pas de JIT dans un composant, pas de parallélisme en WASI 0.3 (plusieurs instances à la place).
- **Deux libc, deux côtés** : wasi-libc pour le C compilé en Wasm (applications), mlibc pour le C natif (système). Ce n'est pas un choix entre les deux.
- **Outils de secours** : uutils coreutils en composants Wasm (cible `wasm32-wasip2` depuis la 0.10, quelques outils ne compilent pas encore). findutils ne vise que WASI 0.1. Shell : brush, qui compile pour `wasm32-wasip3` à titre expérimental ; nushell ne compile pas pour WASI. Présents dans l'emplacement de récupération, utilisables par nous et par l'agent.
- **Applications web** : les interfaces WIT accordées par le manifeste apparaissent comme modules ES (`import { open } from "os:core/store"`), avec la correspondance de jco (ressource en classe, `result` en exception, async en `Promise`, flux en `ReadableStream`). Réservé aux paquets signés, jamais aux sites ordinaires.
- **Quatre façons de dessiner**, de la plus simple à la plus libre : catalogue DodOS (le même que l'agent), bibliothèque d'interface du système (gpui) compilée en Wasm, application web (HTML, CSS, JS dans LibWeb), WebGPU brut.
- **Applications Tauri** : le modèle est le même (interface web dans le moteur du système, backend Rust). Le backend se recompile en composant Wasm si ses dépendances le permettent.
- **Actions** : toute application exporte ses actions typées avec leur classe d'effet. C'est ce qui la rend pilotable par l'agent.
- **Portage de code existant** : wasi-libc. Les fichiers y sont déjà des handles pré-ouverts, ce qui correspond à la règle 2.
- **Débogage** : DWARF dans Wasm avec lldb en mode hébergé, outils de développement de Ladybird pour les applications web.
- **Promesse** : un composant publié continue de tourner. Le corpus d'anciens binaires en CI la vérifie.

## Ordre de construction (proposé)

Étape 0, avant la première ligne de code : un dépôt modèle (environnement Nix, commande `verify`, `AGENTS.md`, workflow GitHub Actions, file de fusion, `CODEOWNERS`) et le dépôt d'intégration. Chaque nouveau dépôt part du modèle, donc naît avec sa CI. Ce socle ne suffit pas : chaque étape ci-dessous apporte ses propres contrôles (voir « Contrôles par étape » dans le harnais).

Piste hébergée, sur Linux et macOS :

1. Runtime hébergé et outil `dodo` : un composant lit et écrit dans le stockage.
2. Surface : notre compositeur en version hébergée, et un composant qui affiche une interface du catalogue par gpui.
3. Actions et agent : llama.cpp, A2UI, délégation, confirmations.
4. Shell.
5. Magasin de blobs réel sur une image disque, paquets signés.

Piste noyau, sur QEMU puis sur le desktop de référence :

1. Démarrage, capacités, IPC, oracle différentiel.
2. SMP, ordonnancement, premier processus natif.
3. IOMMU, cadre de pilotes, couche d'émulation : NVMe, USB, réseau.
4. Cœur NVIDIA et NVK : un triangle Vulkan.

Convergence : mlibc, bibliothèque standard de Rust sur notre cible, dépendances de Ladybird, compositeur sur scanout réel, portes de latence, puis audio, veille, saisie, accessibilité.

## Harnais des agents de développement

Le but : un agent ne peut ni tricher sur la vérification, ni élargir sa tâche, ni fusionner seul. Méthode tirée de retours d'expérience de 2026 : réécriture du runtime de Copilot en Rust (GitHub, 16 septembre), Copilot Cowork (Microsoft, 2 novembre), Bun de Zig vers Rust (8 juillet), compilateur C d'Anthropic (5 février), harness engineering d'OpenAI (11 février).

**Dans chaque dépôt**

- `AGENTS.md` court, 60 à 100 lignes, écrit à la main : la commande de vérification en tête, trois zones (toujours, demander d'abord, jamais), des renvois vers `docs/`. Un fichier généré automatiquement dégrade les résultats (étude ETH Zurich, arXiv 2602.11988).
- `CLAUDE.md` de quelques lignes qui renvoie à `AGENTS.md`.
- Skills dans `.agents/skills/`, avec un lien `.claude/skills` vers ce dossier : conventions du langage du dépôt, débogage QEMU, rebase et relecture, tri d'un échec d'oracle.
- `docs/` versionné : architecture, décisions, conventions. `AGENTS.md` est la carte, pas le contenu.
- Les règles dures ne vivent jamais dans la prose : elles sont appliquées par la CI, les linters, `CODEOWNERS` et les hooks.

**La CI fait foi**

- Environnement hermétique épinglé par Nix : mêmes outils en local et en CI, donc pas de « ça marche sur ma machine ».
- Une seule commande, `verify`, identique en local et en CI.
- File de fusion : chaque PR est retestée sur le sommet réel de la branche avant d'entrer.
- Chaque contrôle prouve qu'il a contrôlé : il affiche ce qu'il a inspecté, et un test lui injecte une faute pour vérifier qu'il échoue.
- Dossiers protégés par `CODEOWNERS` : tests, oracles, workflows, `AGENTS.md`, budgets. Aucun label de dérogation qu'un agent puisse poser.
- Budgets à cliquet, qui ne peuvent que baisser sans accord : `unsafe`, taille du noyau et des images, dépendances et licences (`cargo-deny`).
- Paliers : tests hébergés et QEMU avec KVM à chaque PR ; fuzzing différentiel et longues matrices la nuit ; matériel réel et portes de latence sur le desktop de référence, jamais déclenchés par une PR non relue.
- Infrastructure gratuite : GitHub Actions pour les dépôts publics (Linux x86 avec KVM), Cloudflare R2 pour les caches et les blobs, le desktop de référence comme runner auto-hébergé.
- Un dépôt d'intégration épingle le commit de chaque dépôt. Un changement de `os:core` déclenche les tests des dépôts qui en dépendent.

**Contrôles par étape (proposé)**

Règle : un contrôle entre dans la CI en même temps que le code qu'il garde, jamais après.

- Socle, tous dépôts : format et lint ; build reproductible (deux builds, mêmes octets) ; tests ; chaîne d'approvisionnement (`cargo-deny`, `cargo-vet`, actions GitHub épinglées par SHA, aucun secret pour une PR non relue) ; test de mutation la nuit (une faute injectée dans le code doit faire échouer un test).
- Code `unsafe` et frontière Zig/Rust : Miri, sanitizers en mode hébergé, Kani.
- Noyau : oracle différentiel contre seL4 ; Verus sur la logique Rust ; simulation déterministe des messages entre cœurs (ordres et pannes rejoués depuis une graine) ; démarrage sous QEMU ; fuzzing des appels système.
- ABI : détection d'un changement cassant de WIT ; corpus d'anciens binaires ; suite WASI.
- Performance : comptes de cycles déterministes sous QEMU à chaque PR ; portes de latence et de surcoût sur le desktop de référence la nuit, avec seuil statistique ; bissection automatique d'une régression.
- Matériel dans la boucle : alimentation pilotée, console série capturée, image flashée automatiquement.
- Userland : WPT pour le web ; captures d'écran de référence pour le compositeur et le catalogue ; contrôles d'accessibilité.
- Publication : image signée et reproductible, SBOM, test de mise à jour et de retour arrière.
- La CI elle-même : chaque contrôle a son test d'injection de faute ; un test instable est mis en quarantaine avec un ticket, jamais relancé jusqu'au vert.

**Workflow de développement (proposé)**

- Tronc unique par dépôt, branches courtes, PR obligatoire, file de fusion, historique linéaire, commits signés. Une régression se traite par un retour arrière d'abord, le correctif ensuite.
- Trois voies selon ce que touche le changement :
  1. Contrat (noyau, `os:core`, format de paquet, modèle de sécurité) : une fiche de décision relue par les deux humains, puis le modèle exécutable et les tests, puis le code.
  2. Fonction : brief, tests, agent, relecture, fusion (le cycle ci-dessous).
  3. Entretien (dépendances, documentation) : PR directe, un relecteur.
- L'ordre pour le noyau ne s'inverse jamais : spécification, modèle, oracle, implémentation.
- Fiches de décision numérotées dans `docs/decisions/` de chaque dépôt ; `DIRECTION.md` ne garde que le résumé.
- Entre dépôts : un changement de contrat est une PR dans le dépôt du contrat, puis un déplacement d'épingle dans le dépôt d'intégration, qui relance les tests des dépendants.
- Définition de « fini » : `verify` vert, portes tenues, documentation à jour, aucun budget à cliquet relâché.
- Rythme : image nocturne, image hebdomadaire testée sur le matériel, version quand les portes sont tenues.

**Cycle d'une tâche**

1. Un humain écrit le brief (but, dépôt, fichiers autorisés, zones interdites, état final attendu) et écrit ou valide les tests avant le code. Pour le noyau et l'ABI, une partie des tests reste invisible à l'agent.
2. L'agent travaille dans un worktree, sans aucun secret, jusqu'à ce que `verify` passe. Au-delà d'un nombre fixé de tours ou de trois échecs identiques, il s'arrête et remonte.
3. Porte anti-triche : le nouveau test doit échouer sans le correctif. Aucun bouchon, aucun `todo!()`, aucun contournement justifié par un paragraphe.
4. Relecture par des agents à contexte vierge, d'une autre famille de modèles, qui ne reçoivent que le diff, le brief et les contrats : deux relecteurs pour le noyau et pour l'ABI, un pour l'userland.
5. File de fusion, puis fusion par un humain.

**Pièges documentés à éviter**

- « Si ça compile, c'est juste » est faux : des dizaines de régressions sémantiques ont passé le compilateur chez GitHub.
- Des agents ont supprimé un test pour masquer un oubli, et posé eux-mêmes un label de dérogation.
- Des contrôles sont tombés à zéro fichier inspecté sans que personne le voie.
- Trop de compilations en parallèle gèlent la machine : un seul build à la fois par machine.
- Un brief vague (« porte X ») produit un travail qui évite les parties difficiles.

## Redémarrage et remplacement à chaud

Tout composant du système se redémarre ou se remplace sans redémarrer la machine. Le noyau a son propre mécanisme (formats d'objets versionnés).

- **Pilote** : le gestionnaire arrête le processus, réinitialise le périphérique au niveau du bus (réinitialisation de fonction PCIe ou cycle d'alimentation), recrée son domaine IOMMU, relance le pilote. L'interface de classe décide du sort des requêtes en cours : rejouées pour le disque, perdues pour le réseau, dernière image conservée pour l'affichage.
- **Service** : son état durable vit dans le stockage et dans la table de handles persistante. Les clients reçoivent l'erreur `gone` ou se reconnectent, ce que la règle 1 de l'ABI impose déjà de savoir traiter.
- **Coût** : une pause, pas un blocage. La pause est visible quand il s'agit du disque système ou du GPU.

## Panne et arrêt (proposé)

Principe : l'arrêt et la panne suivent le même chemin (logiciel « crash-only », Candea et Fox 2003, de mémoire). Si l'état sur disque est cohérent à tout instant, éteindre n'a rien à ranger, et la reprise après panne est testée à chaque arrêt.

- **Un composant ou un service tombe** : redémarrage ci-dessus, état repris depuis son instantané.
- **Coupure de courant** : les blobs sont immuables et la racine du stockage bascule de façon atomique, donc pas de vérification du disque au redémarrage. Les objets modifiables sont versionnés. Les processus sont pris en instantané à intervalle régulier : on perd au plus quelques secondes de saisie. Intervalle à fixer.
- **Panique d'un noyau de cœur** (proposé sur demande de l'utilisateur ; remplace « on arrête tout ») : un noyau qui panique redémarre seul, la machine continue. Les noyaux ne partagent pas d'état et se parlent par messages, donc la panne d'un seul est celle d'un nœud dans un système réparti.
  1. Confinement : chaque noyau ne mappe que sa propre mémoire, et valide tout message reçu d'un autre noyau. Sans cela, un noyau fautif peut écrire chez ses voisins et rien n'est garanti.
  2. Détection : panique, battement entre noyaux, erreur matérielle signalée sur le cœur.
  3. Reprise : les voisins isolent le cœur, le noyau y est rechargé par le chemin normal de mise en route d'un cœur. Les références vers ses objets rendent `gone`, que la règle 1 de l'ABI impose déjà de traiter. Les processus qui y tournaient reprennent depuis leur instantané, sur ce cœur ou un autre. Un pilote suit le protocole de redémarrage.
  4. Plus tard, recherche : adopter l'état de l'ancien noyau après validation, au lieu de repartir des instantanés (Otherworld le fait pour Linux, 97 % de réussite annoncés).
  5. Cœur matériellement défaillant : retiré, la machine continue avec les autres.
  - Arrêt complet seulement si le confinement lui-même est violé ou si la panne se répète. Trace écrite dans une zone réservée, puis redémarrage.
  - Le même chemin sert à remplacer le noyau cœur par cœur : mise à jour du noyau sans redémarrage.
  - Contrôle : la simulation déterministe tue un noyau au hasard à chaque fusion et vérifie que le reste survit. Porte à fixer : durée de reprise d'un cœur.
  - Conséquence sur le choix ouvert du multithread : le journal répliqué (NrOS) est un état partagé entre noyaux, plus difficile à rendre sûr si un noyau meurt en pleine écriture ; les groupes de cœurs par messages s'y prêtent mieux.
  - Antériorité (recherche web du 14 novembre 2026, résumés seulement) : Barrelfish/DC remplace le noyau d'un cœur à chaud, sans évaluation de panne trouvée ; Quest-V reprend après panne mais isole ses noyaux par virtualisation ; Kmorph (Linux, hors arbre) tient un noyau de secours qui reprend la machine en une seconde environ. Candidat à un quatrième axe à revendiquer, argument fort côté serveur ; à faire vérifier.
- **Blocage** : chien de garde matériel armé par le noyau, battement par service surveillé par le gestionnaire.
- **Boucle de redémarrage** : emplacements A/B/R, retour arrière automatique (déjà aligné).
- **Boîte noire** : tampon circulaire des dernières secondes de messages par tâche, toujours actif, joint au rapport de panne. Le rapport reste local ; l'agent peut l'expliquer.
- **Arrêt demandé** : dernier instantané, bascule de la racine, coupure. Les périphériques sont réinitialisés au démarrage, pas à l'arrêt.

## Stockage : zones et portée (proposé)

Pas d'arborescence globale. Le disque porte deux partitions, et le stockage se découpe en zones qui diffèrent par leur portée, leur chiffrement, leur sauvegarde et leur durée de vie.

Partitions : (1) partition EFI en FAT32, imposée par le firmware, qui porte les images de démarrage signées des emplacements A/B/R et n'est écrite que par la mise à jour ; (2) notre magasin, qui porte tout le reste, plus une petite région brute pour la trace de panne.

| Zone | Contenu | Portée | Chiffrée | Octets copiés dans la sauvegarde de l'utilisateur | Durée de vie |
|---|---|---|---|---|---|
| Système | Blobs de l'image, désignés par le hash du système | Machine, lecture seule | Non (public, vérifié) | Non : la sauvegarde garde le hash du système, les blobs se retéléchargent | Jusqu'au retrait de l'emplacement |
| Paquets | Blobs et manifestes des applications, modèles | Machine, partagés entre utilisateurs | Non | Non : la sauvegarde garde la liste des paquets et leurs hash ; option « copie complète » pour un usage hors ligne | Ramasse-miettes par références |
| Cache | Code compilé, vignettes, index | Machine ou utilisateur | Selon l'origine | Non | Effaçable à tout moment |
| Appareil | Clés d'appairage, réseaux, réglages matériels | Machine, disponible avant la session | Oui, clé du TPM | Non | Jusqu'à la remise à zéro |
| Utilisateur | Collections de la personne, mémoire de l'agent, versions | Un utilisateur | Oui, clé de l'utilisateur | Oui | Permanente |
| Application | La collection `home` reçue au lancement | Un utilisateur et une application | Oui | Oui | Retirée avec l'application, sur confirmation |
| Instantanés | État figé des processus | Un utilisateur | Oui | Non, sauf déplacement de surface | Remplacé à chaque prise |
| Éphémère | Fichiers temporaires, session invitée | Une tâche ou une session, en mémoire | Sans objet | Non | Fin de la tâche |
| Étranger | Clés USB, disques d'autres systèmes, partages réseau | Vu comme une collection, par un composant lecteur | Selon le support | Non | Tant que le support est branché |

- Le format sur disque ne change pas (ligne « Stockage » des décisions) : SQLite pour les métadonnées, blobs immuables pour les données. Les zones sont des portées logiques dans ce magasin, pas des systèmes de fichiers séparés.
- Comparaison avec Fuchsia (vérifié le 14 novembre 2026, documentation officielle) : bootfs (image en lecture seule chargée au démarrage) correspond à notre image de démarrage signée ; blobfs (paquets, adressés par contenu) à nos zones système et paquets ; minfs puis Fxfs (données modifiables) à nos objets. Fuchsia a accepté de ranger les blobs dans Fxfs et de supprimer son gestionnaire de volumes (RFC-0225) : un seul magasin, comme nous.
- La vue POSIX des logiciels portés est fabriquée par la table de noms du processus : `/tmp` vers la zone éphémère, le dossier personnel vers la zone d'application.
- Remise à zéro : effacer les zones appareil et utilisateur. Embarqué : zones système et appareil seulement.
- Réponses proposées aux points ouverts ci-dessous : (1) un second type d'objet, modifiable par extents, copie sur écriture, somme de contrôle par bloc, sans arbre de Merkle ; ses versions sont des instantanés ; les bases SQLite des applications y vivent. (2) Un disque pour le magasin en v1 ; un autre disque est un magasin de plus où placer des zones ; miroir plus tard. (3) Le quota est porté par la capacité de la collection. (4) Toutes les versions pendant 30 jours, puis une par jour, puis une par semaine ; réglable. (5) Pas de mémoire d'échange en v1 (voir pression mémoire). (6) Accepté ; une installation privée va dans la zone de l'utilisateur.
- Ouvert : (1) objets très modifiés (base de données d'une application, image disque) : une suite de blobs immuables coûte cher en écritures aléatoires, il faut sans doute un type d'objet modifiable par extents, sans arbre de Merkle ; (2) plusieurs disques, miroir ; (3) quotas par application ; (4) durée de garde des versions ; (5) mémoire d'échange : compression d'abord, région chiffrée ensuite, à décider ; (6) les paquets installés par un utilisateur sont visibles des autres, à accepter ou non.

## IOMMU

- Chaque processus pilote reçoit un espace d'adresses d'entrée-sortie, objet du noyau désigné par une capacité. Le périphérique ne peut atteindre par DMA que la mémoire explicitement placée dans cet espace.
- Les tampons de données sont des objets mémoire partagés, visibles à la fois du client, du pilote et du périphérique : les files sans copie restent possibles.
- Mappages durables (réserves de tampons) plutôt qu'un mappage par requête, pour limiter le coût.
- Remappage des interruptions activé : un périphérique ne peut pas en forger.
- Les périphériques que le matériel ne sait pas séparer vont dans le même processus pilote.
- IOMMU active avant le démarrage du premier pilote. Sur une machine sans IOMMU, les pilotes sont déclarés de confiance, et c'est affiché.
- Les fonctions `dma_map` de l'émulation Linux se traduisent directement vers cet objet.

## Pilotes en micro-VM : alternative non retenue

Principe : un Linux minimal dans une machine virtuelle par pilote, le périphérique passé par l'IOMMU, les données par les mêmes files partagées. LionsOS (seL4) le fait en repli pour le réseau, le disque, le son et un GPU 2D.

- **Pour** : tout pilote Linux marche sans modification, y compris Wi-Fi, Bluetooth avec BlueZ et le pilote NVIDIA propriétaire (CUDA, DLSS, décodage vidéo complet) ; aucune couche d'émulation à écrire ni à maintenir ; montée de version du noyau triviale ; isolation équivalente.
- **Contre** : un hyperviseur à ajouter au noyau, donc plus de code de confiance et plus de tests hors oracle ; 50 à 250 Mo de mémoire et un démarrage de Linux par VM (ordre de grandeur, de mémoire) ; redémarrage d'un pilote en secondes ; interruptions qui traversent la VM, donc latence ; veille à coordonner avec chaque invité ; GPU : le scanout et l'ordonnancement resteraient dans l'invité, ce qui casse les portes de latence et le rôle du service GPU. Aucun chiffre de surcoût publié.
- **Position** : couche d'émulation sur le chemin critique. La micro-VM reste un repli possible pour la longue traîne (Wi-Fi, Bluetooth, matériel exotique), à rouvrir seulement si l'émulation cale.

## Sécurité, isolation et modularité (proposé)

Il n'y a pas de conteneur parce qu'il n'y a rien à contenir : aucun nom global, aucune autorité ambiante. Chaque programme est d'origine ce qu'un conteneur cherche à obtenir après coup.

**Trois frontières, de la moins chère à la plus forte**

- **Composant Wasm** : frontière entre les parties d'une même application, y compris ses dépendances. Une bibliothèque tierce ne reçoit que les imports qu'on lui passe. Coût : un appel de fonction et la copie des arguments.
- **Processus** : frontière entre éditeurs. Un processus par éditeur (ou par site web), jamais deux éditeurs dans le même espace d'adresses, à cause des canaux auxiliaires de type Spectre. Coût : un IPC.
- **Domaine IOMMU** : frontière entre un pilote, son périphérique et le reste de la mémoire.

**Chaîne de confiance**

- Firmware, image de démarrage signée, puis le système, qui est un hash. Chaque blob est vérifié à la lecture par son arbre de Merkle : au redémarrage, la machine est exactement ce hash.
- Tout code exécutable descend d'un blob signé. Seul le service de compilation produit du code machine, mis en cache par hash du composant, version du compilateur et jeu d'instructions. Les applications ne peuvent pas créer de page exécutable. Seule exception en discussion : le JIT du processus web.
- L'utilisateur peut inscrire ses propres clés : la machine reste la sienne.

**Blobs**

- Dédupliqués par contenu entre tous les paquets : une bibliothèque commune à dix applications est stockée une fois, et compilée une fois.
- Rien à monter ni à préparer au lancement.
- Limite : un composant qui embarque ses dépendances ne partage rien. Les runtimes de langage (Python, JS) sont donc livrés en composants séparés, identiques d'une application à l'autre.

**Modularité**

- Chaque service est défini par son monde WIT, donc remplaçable. Le câblage des capacités entre composants est déclaratif, et fait partie du hash du système.

**Agent**

- La provenance suit les données : une tâche qui a lu du contenu non fiable est marquée, et ses effets externes demandent une confirmation. L'injection de prompt est contenue par le système, pas par le modèle.

**Coûts attendus**, à mesurer : exécution Wasm 1,5 à 2,4 fois le natif (le poste principal) ; copie aux frontières de composants (d'où la règle 6) ; un hash par bloc à la première lecture d'un blob ; IOMMU presque nulle avec des mappages durables.

## Audio

- **Pilotes** : pilotes son de Linux (HDA Intel, USB audio) dans la couche d'émulation. Ils exposent un tampon circulaire en mémoire partagée.
- **Service audio** écrit par nous (celui de Fuchsia est lié à ses IPC et n'a pas été extrait), natif, avec un budget d'ordonnancement garanti : graphe de mixage tiré par l'horloge du périphérique, quantum fixe de 128 trames à 48 kHz (2,7 ms). Modèle de PipeWire et de CoreAudio, sans reprendre leur code.
- **Clients** : tampons circulaires en mémoire partagée, aucun message par tampon. Web Audio pour les applications web, une interface WIT pour les composants.
- **Droits** : lecture, microphone et capture du son des autres applications sont trois capacités distinctes. Le microphone a son indicateur dessiné par le compositeur.
- **Agent** : le détecteur de mot d'éveil est un composant qui n'a que le microphone en entrée et un signal en sortie, sans réseau ni stockage. Annulation d'écho par le module audio de WebRTC, pour pouvoir interrompre l'agent pendant qu'il parle.
- **Bluetooth** : dans Linux, les pilotes (btusb) ne font que transporter les paquets HCI ; la pile hôte est dans le noyau et les profils audio dans BlueZ. On ne porte que le pilote de transport. Pile hôte, piste retenue en premier (décidé) : Sapphire de Fuchsia (hôte déjà extrait dans Pigweed) avec les composants de profils de l'arbre Fuchsia (bt-a2dp, bt-hfp-audio-gateway, bt-avrcp, bt-hid, bt-rfcomm), à adapter de FIDL vers WIT, comme pour Netstack3. Autres pistes : BlueZ complet (demande d'émuler les sockets Bluetooth et D-Bus) ; Zephyr (Bluetooth classique maintenu par NXP, HFP encore expérimental, portage hors Zephyr au stade de prototype, un seul contrôleur) ; Android (énorme). Pile de FreeBSD écartée : peu de Bluetooth basse consommation, audio par bricolage. Pas sur le chemin critique du desktop.

## Énergie et veille

- **ACPI** par uACPI (MIT, version 7.0.0 d'octobre 2026, conçu pour être embarqué), plutôt qu'ACPICA. Nécessaire de toute façon pour énumérer le matériel.
- **Desktop** : pas de veille au début. Écran éteint, états de repos du processeur, fréquence gérée par le matériel (HWP).
- **Portable** : veille moderne (s2idle), la seule que les portables Intel récents proposent. La couche d'émulation doit alors rejouer les rappels de mise en veille des pilotes Linux, dans l'ordre.
- **Reprise après veille** : un pilote qui ne se réveille pas est redémarré selon le protocole de redémarrage ci-dessus. La couche d'émulation doit gérer les états D3.
- **Mot d'éveil pendant la veille : objectif, pas encore acquis.** Les portables Intel récents ont un processeur de signal basse consommation qui reste alimenté en veille, et le firmware ouvert SOF sait y faire tourner un détecteur de mot-clé qui réveille la machine. Obstacle : ce firmware doit être signé par le constructeur, donc on ne peut charger que le firmware signé existant et y injecter un modèle s'il contient le module voulu. À tester sur le Dell. Windows a retiré cette fonction en 24H2 pour des raisons de consommation. Sur desktop, pas de tel processeur : veille légère avec détecteur sur le CPU, ou petit micro USB à microcontrôleur qui réveille la machine.

## Saisie

- **Chaîne** : pilotes Linux (USB HID, I2C HID) qui produisent des événements evdev, libinput porté pour le pavé tactile et les gestes (il faut aussi lui émuler la découverte de périphériques de udev), xkbcommon pour les dispositions de clavier.
- **Le compositeur possède le focus** et dessine le curseur sur le plan matériel, directement depuis les événements d'entrée.
- **Sécurité** : seule la surface au focus reçoit les touches. Les raccourcis globaux et l'injection d'entrées sont des capacités que personne n'a par défaut.
- **Méthodes d'entrée** : un protocole de saisie de texte (texte environnant, pré-édition, validation, rectangle du curseur), sur le modèle de text-input de Wayland. Un moteur de saisie est un composant sans réseau. Clavier virtuel, sélecteur d'émojis et dictée vocale de l'agent passent par ce même protocole.
- **Moteurs** : librime (chinois, BSD, portable), libhangul (coréen, LGPL, donc en composant séparé), mozc (japonais, très lourd à compiler : Bazel et JDK). Plus tard.

## Accessibilité

- **Format d'arbre à décider.** Ladybird a son propre arbre, exporté vers NSAccessibility et AT-SPI2 (PR 9156), et a écarté AccessKit pour le contenu web : il lui manque la recherche par prédicat et les marqueurs de texte. AccessKit reste valable pour le shell.
- **Le catalogue DodOS est sémantique par construction** : ses interfaces sont accessibles sans travail en plus.
- **Lecteur d'écran** déterministe, écrit par nous sur ces arbres, avec la synthèse vocale de l'agent. L'agent ne le remplace pas.
- **Dans le compositeur** : loupe, filtres de couleur, contraste élevé par les jetons de thème, réduction des animations.
- **Sous-titres en direct** par le modèle de reconnaissance vocale local.
- **Lire l'arbre d'une autre application est une capacité**, accordée par l'utilisateur aux outils d'assistance. Elle sert aussi de repli à l'agent pour les sites web, qui n'exportent pas d'actions.

## Design system (en discussion)

- **Principe : une présence, pas une fenêtre.** Vaut pour l'agent et pour tout l'userland natif que nous livrons : réglages, fichiers et autres sont des services qui exportent des actions et des vues du catalogue, affichées par le shell, sans cadre d'application.
- **Un seul jeu de jetons**, trois moteurs de rendu (gpui, CSS dans LibWeb, catalogue A2UI). Format : Design Tokens 2025.10 (première version stable, rapport d'un groupe communautaire du W3C, hors voie de standardisation), avec son module de résolution pour les thèmes.
- **Sémantique, jamais stylistique** : l'agent et les applications du catalogue n'émettent que des intentions (`tone`, `text-style`).
- **Assemblage des inspirations** : les rôles de Material 3 Expressive (rôles de couleur dérivés d'une couleur source, échelle typographique, échelle de formes, mouvement à ressorts), sans ses composants mobiles ; les proportions et la retenue d'Adwaita (densité bureau, contenu d'abord) ; le verre dépoli de COSMIC (flou Dual Kawase, livré dans COSMIC 1.3.0).
- **La matière porte la confiance** : le verre dépoli est réservé au système et à l'agent. Seul le compositeur voit les pixels des autres surfaces, donc une application ne peut pas l'imiter. Les applications ont des surfaces tonales opaques. Réglage d'opacité pour l'accessibilité.
- **Identité visuelle** de qui parle (agent, application, système), des quatre classes d'effet et de la provenance.
- **Mouvement** piloté par le compositeur, interruptible, soumis aux portes de latence.
- **Coût du framework** : une application qui embarque gpui le paie à chaque fois (liaison statique, 8 à 15 Mo cités par un guide, à mesurer ; plus son propre atlas de glyphes et son contexte GPU). Une application du catalogue ne paie rien : le rendu est dans le shell, c'est notre équivalent d'une bibliothèque partagée. Conséquence : notre userland natif s'écrit contre le catalogue, qui devra s'étendre au-delà des quinze types de l'agent.
- **Verre pour les applications** : réservé au système au départ (décidé). S'il s'ouvre un jour, ce sera une matière fournie par le compositeur et visiblement distincte de celle du système.
- **Catalogue, proposition** : deux niveaux, dans deux interfaces WIT versionnées à part. Niveau agent : les quinze types actuels. Niveau application : une quinzaine de plus (liste virtuelle alimentée par un flux, arbre, onglets et navigation latérale, menu, dialogue, éditeur de texte, curseur, recherche, zone de dessin). Critères d'entrée d'un type : sémantique et non visuel, accessible par construction, rendu identique dans les trois moteurs, mise en page adaptative sans position absolue. WIT est la source, le catalogue A2UI en est généré. Tout le reste passe par une échappatoire : applet, surface WebGPU ou vue web. Test : captures de référence par type et par thème.
- **Icônes (décidé)** : Material Symbols en variante Rounded (Apache-2.0, police variable à quatre axes : remplissage, graisse, grade, taille optique), en sous-ensemble. `core.wit` expose nos propres noms sémantiques, figés, associés aux glyphes : le jeu reste remplaçable sans casser l'ABI.
- **À surveiller** : ReactiveScript (solidjs, MIT, version 0.1 expérimentale d'octobre 2026), un langage d'interface réactive vérifié à la compilation et conçu pour être écrit juste par une IA. Compile vers Solid 2.0, donc vers le DOM. Piste possible pour les applets et les applications web, rien à adopter aujourd'hui.

## Les règles de l'ABI

1. Tout appel sur une capacité peut échouer, puisqu'elle est révocable.
2. Aucun nom global : un chemin n'existe que relativement à un handle.
3. L'identité d'un composant est sa clé d'éditeur plus son nom.
4. L'asynchrone est le défaut.
5. Les objets du stockage ont des identifiants stables.
6. Les gros volumes passent par des handles de tampon ou des flux, jamais par valeur : c'est la seule copie que le compilateur ne peut pas retirer.

Premier jet des mondes `app` et `agent` : [core.wit](core.wit), validé par `wasm-tools 1.263`.
Limites connues : la classe d'effet d'une action passe par une interface dynamique. WIT a des annotations de version (`@since`, `@unstable`, `@deprecated`), mais pas d'annotations libres.

L'arbre d'interface est validé par le système à chaque mise à jour : parent existant, action présente dans la portée de la tâche, plafonds de taille. Les applications Wasm accèdent au GPU par `wasi:webgpu` (phase 2), sans passer par LibWeb.

## L'agent

- Il agit par les actions typées que chaque application exporte, jamais en cliquant sur des pixels. Les services système (réglages, fenêtres, réseau, installation, énergie) exportent la même interface : gérer l'OS n'est pas une API à part.
- Trois sorties : actions, interface 2D déclarative, applets (3D et cas libres). Les applets sont des objets du stockage, réutilisés et alimentés en données plutôt que régénérés.
- Quatre classes d'effet : lecture, écriture réversible, irréversible, externe. Les deux dernières demandent une confirmation dessinée par le compositeur.
- Il n'a aucune autorité propre : chaque tâche reçoit des droits délégués, journalisés, annulables.
- Aucun composant ne cumule données privées, contenu non fiable et communication externe.

## Portes de latence

Cibles à calibrer sur la machine de référence, à 120 Hz, mesurées par photodiode par rapport à un scanout nu.

| Porte | Cible |
|---|---|
| Curseur, entrée → photon | ≤ 1 image |
| Touche → glyphe affiché | ≤ 2 images au p99 |
| Défilement pendant qu'un moteur de rendu est occupé | 0 image perdue au p99,9 |
| Plein écran WebGPU | 0 image ajoutée |
| Rythme des images pendant une inférence locale | < 0,1 % d'images manquées |
| Tampon de sortie audio | ≤ 5 ms |
| Agent : accusé visuel, puis premier son | ≤ 100 ms, puis ≤ 400 ms |
| Lancement à froid avec cache | ≤ 200 ms jusqu'à la première image |
| Démarrage : passage de main du firmware → première image (proposé) | ≤ 1 s |
| Démarrage : passage de main du firmware → shell utilisable (proposé) | ≤ 2 s |
| Arrêt : demande → coupure (proposé) | ≤ 1 s |
| Sortie de veille → première image (proposé) | ≤ 0,5 s |

Démarrage et arrêt : seL4 ne publie pas de banc de démarrage (cherché le 14 novembre 2026 ; seul chiffre voisin, 1,3 s pour une pile de trois processus sur Cortex-A9, article PARseL). L'oracle ne sert donc pas ici ; la référence est Linux, Windows et macOS sur la même machine, à mesurer. Le temps du firmware n'est pas à nous : on le mesure à part, et on publie aussi le total bouton → image. Leviers : une seule image EFI, services lancés au premier usage de leur capacité, code Wasm déjà compilé en cache, vérification des blobs à la lecture, pilotes démarrés en parallèle, shell rendu depuis son instantané. Point long probable : le chargement du firmware du GPU (à mesurer).

## Portes de surcoût (proposé)

Chaque couche d'isolation a un budget, mesuré à chaque fusion contre une référence sur la même machine. Les cibles sont à calibrer par la mesure ; une porte ne peut ensuite que se resserrer.

| Porte | Référence | Cible de départ |
|---|---|---|
| IPC aller-retour entre deux processus, même cœur | seL4 : environ 740 cycles l'appel et 600 la réponse sur Skylake | < 1,2 fois seL4 (décidé) |
| IPC aller-retour entre deux cœurs | IPC même cœur | À fixer |
| Opération sur l'espace d'adresses d'un processus à plusieurs cœurs (mappage, révocation) | Linux | À fixer |
| Calcul Wasm (étage Cranelift) | Même code compilé en natif | ≤ 1,5 fois, puis ≤ 1,2 fois avec l'étage optimisé |
| Appel entre deux composants du même processus | Appel de fonction natif | À mesurer, avec et sans asynchrone |
| Lecture et écriture disque | Périphérique NVMe brut | ≥ 90 % du débit |
| Débit réseau | Linux sur la même carte | ≥ 90 % |
| IOMMU active | Même charge, IOMMU coupée | ≤ 3 % |
| Vérification des blobs | Lecture sans vérification | ≤ 5 % à froid, 0 à chaud |
| Mémoire d'un processus applicatif vide | | À fixer |
| Stockage d'une application de démonstration | Même application sous Flatpak | Plus petit |

**Leviers de performance Wasm**, en plus des trois étages de compilation (vérifiés le 13 novembre 2026 sauf mention) :

- Proposition `wide-arithmetic` : sur le banc libsodium, Wasmtime 46 passe de 2,41 à 1,46 fois le natif, Wasmer 7.1 de 2,08 à 1,33. Le banc est cryptographique, donc ce gain ne se généralise pas tel quel ; il montre que l'écart vient en partie d'instructions manquantes.
- Segue : la base de la mémoire dans un registre de segment, gain médian de 7,8 % sur SPEC. Option de Wasmtime.
- Clés de protection mémoire (ColorGuard) : moins d'espace d'adresses réservé par instance. Option de Wasmtime.
- Inlineur de Cranelift, y compris entre composants : 1,26 fois sur un banc, désactivé par défaut à sa sortie.
- Traduction Wasm vers C puis compilateur natif (wasm2c) : au niveau des meilleurs runtimes. Piste sérieuse pour l'étage optimisé, puisqu'elle réutilise LLVM sans backend à écrire.
- Langages interprétés (JS, Python, Lua) : évaluation partielle par weval, 2 à 5 fois plus rapide que l'interpréteur, encore en bêta.
- SIMD et SIMD relâché, appels terminaux : de mémoire.

Le runtime de la NASA (SpaceWasm, JPL) est un interpréteur Wasm 1.0 conçu pour la sûreté et le déterminisme, pas pour la vitesse : rien à en tirer sur ce point.

## Ordonnancement (proposé)

Le mécanisme est dans le noyau, la politique en espace utilisateur.

- **Dans chaque noyau de cœur** : une file locale, sans verrou. Un thread ne tourne que s'il détient un contexte d'ordonnancement, objet désigné par une capacité, qui porte un budget, une période, une échéance et une classe de cœur (modèle de seL4 MCS, de mémoire). Le noyau choisit l'échéance la plus proche parmi les contextes qui ont du budget, et ne déplace jamais un thread de lui-même.
- **Le budget suit l'appel** : quand un client appelle un service, le service tourne sur le budget du client. Un service n'a pas de temps propre, donc il ne peut ni en voler ni être affamé, et le coût d'une tâche de l'agent se compte de bout en bout.
- **Service de placement, en espace utilisateur** : il décide quel contexte va sur quel cœur, et demande les migrations par messages. Il connaît les types de cœurs, la charge, la température et l'énergie. Remplaçable sans toucher au noyau (leçon de `sched_ext`).
- **Classes** : image (entrée, compositeur, audio) sur les cœurs rapides, avec réserve garantie ; interactif ; fond (compilation, indexation, inférence longue) sur les cœurs économes, préempté à chaque période.
- **Horloge** : pas de tic. Le rafraîchissement de l'écran ouvre chaque période ; un minuteur à échéance couvre le reste.
- **GPU** : le service GPU applique les mêmes classes aux soumissions, dans le même graphe d'échéances.
- **Dans un processus** : le runtime Wasm ordonne ses tâches asynchrones de façon coopérative ; le noyau ne voit que des threads.
- **Admission** : créer un contexte de classe image est refusé si la somme des budgets dépasse la période.
- **Repos** : un cœur sans contexte est mis au repos par son noyau ; le service de placement regroupe la charge pour endormir des cœurs.

Trois points de conception (proposé, 14 novembre 2026) :

- **Inversion de priorité sur un service partagé.** Le cas : un client de fond est dans le service quand un client de classe image arrive. Quatre règles. (1) Un service a un thread passif par cœur, donc un appel reste sur le cœur de l'appelant et deux cœurs ne s'attendent pas. (2) Prêt : le client qui attend prête son contexte (budget et échéance) à celui qui est servi, jusqu'à ce que le service se libère. (3) Seuil à l'entrée : un appel n'entre que si le budget restant couvre le pire cas déclaré de l'appel (le contrat de latence de la capacité) ; sinon il attend sa recharge dehors. seL4 MCS a ce problème ouvert et le même remède en proposition (RFC-14, seuils de budget sur les endpoints, non fusionné à notre connaissance). (4) Épuisement malgré tout : faute de délai vers le superviseur du service, la requête est annulée, le service revient à son état d'avant. Un service doit donc écrire des requêtes annulables.
- **Groupe de cœurs d'un processus multithread.** Un processus détient un groupe de cœurs : l'ensemble des cœurs où son espace d'adresses est actif. Les opérations sur l'espace d'adresses (mappage, révocation, invalidation de TLB) ne concernent que ce groupe. Le service de placement agrandit ou réduit le groupe selon la charge ; c'est ici que se branche la structure dynamique. Le budget est une réserve du groupe, où chaque contexte par cœur puise des tranches. Un groupe est d'un seul type de cœur par défaut. Le noyau notifie le runtime du nombre de cœurs qu'il a à l'instant, pour qu'il dimensionne ses threads au lieu de surcharger (idée des scheduler activations, de mémoire). Un thread préempté alors qu'il tient un verrou : celui qui attend lui prête son contexte, par le même mécanisme de prêt que ci-dessus.
- **Temps passé dans les interruptions.** Les pilotes sont en espace utilisateur : une interruption n'est dans le noyau qu'un acquittement et une notification, de durée bornée. Ce temps est mesuré par horodatage à l'entrée et à la sortie, retiré au thread interrompu et débité au contexte du pilote. Le pilote traite sur son propre contexte ; budget épuisé, sa ligne d'interruption reste masquée jusqu'à la recharge, ce qui borne une tempête d'interruptions. Une complétion d'entrée-sortie est débitée au client dont la requête se termine : la requête porte une tranche de son budget. Les interruptions des périphériques hors classe image sont dirigées vers les cœurs économes ou regroupées en début de période.

Compléments (proposé, 14 novembre 2026) :

- **Qui obtient quelle classe** : la classe image est une capacité. Le shell la remet à la surface au premier plan et aux services de son chemin (entrée, compositeur, audio), et la reprend quand la surface passe derrière. Une application ne peut pas se la donner.
- **Travail de fond** : part équitable entre tâches, pondérée par l'utilisateur ou l'agent ; une part minimale garantie évite la famine.
- **Inférence de l'agent** : classe interactif pendant qu'il répond à l'utilisateur, classe fond sinon ; ses lots GPU sont préemptibles à chaque image.
- **Réveils** : chaque minuteur déclare une tolérance ; le noyau regroupe les réveils dans cette tolérance pour laisser dormir les cœurs.
- **Chaleur et batterie** : le service de placement réduit d'abord les budgets de la classe fond, puis ferme des cœurs rapides ; la classe image est touchée en dernier.
- **Valeurs de départ, à calibrer** : période de la classe image égale à celle de l'écran (8,3 ms à 120 Hz) ; réserve de la classe image plafonnée à la moitié de chaque cœur rapide ; tranche de la classe fond de 10 ms.
- **Contrôles** : simulation déterministe de l'ordonnanceur (mêmes graines que les messages entre cœurs), et les portes de latence.

## Gestion de la mémoire (proposé, 14 novembre 2026)

Même partage que l'ordonnancement : mécanisme dans le noyau, politique en espace utilisateur.

- **Pas de tas dans le noyau.** Toute mémoire dont le noyau a besoin pour un objet vient d'une capacité de mémoire fournie par celui qui crée l'objet (modèle de seL4, de mémoire). Un programme ne peut donc pas épuiser la mémoire du noyau.
- **Mémoire physique par cœur** : chaque noyau a sa réserve de pages, sans verrou ; les réserves se rééquilibrent par messages. NUMA plus tard.
- **Objets mémoire** (modèle de Fuchsia) : un ensemble de pages désigné par une capacité, qui se mappe, se partage et se copie à l'écriture. C'est l'unité de partage entre processus et le support de l'instantané.
- **Pagination en espace utilisateur** : un défaut de page sur un objet adossé au stockage devient un message au service de stockage. Les blobs sont mappés tels quels : le cache de pages est l'ensemble des blobs, partagé par hash entre tous les processus.
- **Espace d'adresses** : les tables de pages sont la seule source de vérité, sans seconde structure à garder cohérente (approche de CortenMM). Invalidation de TLB limitée au groupe de cœurs du processus.
- **Tailles de page** : 2 Mo par défaut pour les mémoires Wasm et le code compilé, 4 Ko sinon. Une mémoire Wasm réserve son espace virtuel avec des pages de garde, ce qui retire les contrôles de bornes.
- **Budget, sans surengagement** : chaque tâche porte un budget mémoire. Une page anonyme est comptée à la tâche au premier accès ; une page de blob partagé est comptée au système. Budget dépassé : erreur d'allocation rendue au runtime, pas de processus tué plus tard par surprise.
- **Pression** : politique du service de mémoire, déjà notée (caches, compression des pages de fond, instantané des surfaces non visibles). Pas de mémoire d'échange en v1.
- **Remise à zéro** : toute page est remise à zéro avant de changer de processus, par les cœurs économes au repos.
- **Mémoire du GPU** : gérée par le service GPU avec les mêmes budgets par tâche. Les poids d'un modèle sont des blobs mappés, partagés entre processus.
- **Pilotes** : mémoire épinglée par une capacité à part, mappages IOMMU durables.
- **Protections** : écriture ou exécution, jamais les deux (déjà noté) ; disposition aléatoire ; pages de garde autour des piles.
- **Portes à ajouter** : coût d'un défaut de page mineur et d'un mappage par rapport à Linux ; mémoire d'un processus vide.
- À concevoir : comptabilité exacte des pages partagées entre deux tâches, mémoire d'une tâche étalée sur plusieurs processus, NUMA, grandes pages de 1 Go pour l'inférence.

## Communication entre appareils (proposé)

Principe : un autre appareil n'est qu'un détenteur de capacités de plus. Tout étant déjà une capacité derrière une interface WIT, exposer un objet, une action ou un périphérique à distance ne demande pas d'API à part (transparence réseau de Plan 9).

- **Identité** : chaque appareil a une clé. L'appairage est un échange de clés par code affiché ou par contact. Les appareils d'une personne forment un cercle, ceux d'un proche reçoivent des capacités limitées.
- **Transport** : connexion directe chiffrée de bout en bout, adressée par clé et non par adresse IP, avec relais en repli. Candidat : iroh (Rust, 1.0 depuis le 15 juin 2026, QUIC, traversée de NAT, protocole stable). Découverte locale par mDNS et Bluetooth basse consommation.
- **Ce que cela donne** : presse-papiers et envoi d'objets ; synchronisation (les blobs immuables adressés par hash se synchronisent sans conflit, les objets modifiables par versions) ; déplacement d'une surface en cours (instantané de processus) ; périphériques prêtés (caméra et micro du téléphone, GPU du desktop pour l'agent du portable) ; un seul agent et une seule mémoire sur tous les appareils ; actions invoquées à distance.
- **Avec les appareils qui ne tournent pas sous DodOS**, le point critique puisque nous n'avons pas de téléphone : (1) l'userland hébergé comme application compagnon sur Android, iOS, Linux, macOS et Windows ; (2) le web : WebRTC, clés d'accès entre appareils ; (3) KDE Connect et LocalSend seulement comme passerelles facultatives, en composants Wasm, pour qui les a déjà : ce ne sont pas le produit, et ils ne sont bien intégrés nulle part (avis de l'utilisateur, 14 novembre). Le produit est notre protocole et notre application compagnon. Téléphones à bootloader libre : DodOS natif, plus tard. À vérifier : ce que les plateformes ouvrent (Wi-Fi Aware sur iOS, interopérabilité Quick Share et AirDrop ; de mémoire).
- À étudier : récepteurs AirPlay, Cast et Miracast ; Matter pour la maison ; règles de conflit des objets modifiables ; révocation d'un appareil perdu.

## Réservoir d'idées (exploration, rien de décidé)

Un nouvel OS est l'occasion d'explorer. Idées connues ou non ; la nouveauté n'est vérifiée pour aucune. Une étoile marque celles que je proposerais d'étudier en premier.

**Bas niveau, noyau**

- ★ Instantané d'un processus comme primitive : l'état d'un composant Wasm est explicite (mémoire linéaire, tables, handles), donc il se fige, se range dans le stockage et reprend. Ouvre la reprise exacte après redémarrage ou mise à jour, la migration vers un autre appareil, le retour arrière. Ancêtres : persistance orthogonale d'EROS et KeyKOS.
- ★ Noyau spécialisé à l'installation : le service de compilation construit le noyau pour la machine exacte (FRED ou IDT, APX, nombre et type de cœurs), sans test de fonctionnalité à l'exécution. Le système étant un hash, chaque variante reste vérifiable.
- La page d'appels système comme optimiseur : puisqu'aucun appel n'est fait en direct, le noyau choisit par machine entre appel immédiat, exécution en mode utilisateur et mise en lot dans un anneau, et peut en changer à chaque version.
- Anneaux de messages comme IPC principal pour l'asynchrone (le défaut de l'ABI), chemin rapide synchrone à côté. Ancêtres : FlexSC, io_uring, sDDF.
- Tables de pages partagées par hash : le code compilé d'un blob est immuable, donc ses pages et leurs sous-arbres de table de pages se partagent entre processus.
- Grandes pages par défaut pour les mémoires linéaires Wasm ; remise à zéro de la mémoire libérée par les cœurs économes au repos.
- Exécution déterministe : les imports d'un composant sont enregistrés, donc une tâche se rejoue à l'identique (audit de l'agent, débogage).

**Performance**

- ★ Compilation optimisée distribuée : l'étage optimisé tourne chez l'éditeur ou sur un service, et le code machine arrive signé, indexé par hash du composant et jeu d'instructions. Pas de LLVM sur la machine. Demande une compilation reproductible. Ancêtre : profils cloud d'ART.
- ★ Lancement par instantané : l'initialisation d'un composant est exécutée à l'installation (comme Wizer), le lancement ne fait que mapper le résultat.
- Caches par hash partagés avec les paquets : pipelines GPU compilés, images décodées, polices rastérisées.
- Préchauffage par l'agent : il connaît l'intention, donc il prépare le composant suivant avant la demande.
- Rôles par type de cœur : chemin de l'image sur les cœurs rapides ; compilation, hachage, indexation et inférence de fond sur les cœurs économes.
- Files NVMe et réseau par cœur, mappées dans le service qui les sert.

**Survie de l'écosystème, sans tout porter de Linux**

- ★ Porter les boîtes à outils, pas les applications : Flutter, Qt, Slint, egui, Dioxus, Tauri et SDL visant `wasi:webgpu` et notre surface apportent leurs applications d'un coup.
- ★ Usine de portage par agents : une chaîne nocturne compile des applications libres en composants Wasm, leurs tests servant d'oracle, et publie celles qui passent.
- ★ Le pilote Linux comme oracle : un agent écrit un pilote natif, et on compare sa trace (MMIO, DMA, interruptions) à celle du pilote Linux sous émulation, comme seL4 sert d'oracle au noyau.
- Pilotes de classe natifs d'abord : NVMe, AHCI, xHCI, classes USB (HID, audio, stockage, caméra, réseau), HDA, HCI Bluetooth, virtio. Une quinzaine de pilotes couvrent la plupart des périphériques.
- Périphériques par le web : WebUSB, WebHID, WebSerial et Web Bluetooth dans notre moteur, adossés à des capacités ; les outils de configuration des fabricants existent déjà sous cette forme.
- L'userland hébergé comme produit : le shell et l'agent tournent sur Linux et macOS avant que le noyau existe, donc l'écosystème démarre sans attendre le matériel.
- Surface distante : une application Linux ou Windows tournant sur une autre machine ou dans le cloud s'affiche comme une surface. Les VM locales restent hors périmètre.
- L'agent remplace la longue traîne : un applet généré à la demande tient lieu de petite application.
- Lecteurs de formats et de systèmes de fichiers étrangers en composants Wasm, pour importer ses données.
- Une machine de référence vendue ou recommandée, plutôt que tous les PC.

**Expérience**

- ★ Rien ne se ferme, rien ne se perd : avec l'instantané de processus, un redémarrage ou une mise à jour rend chaque surface dans son état exact.
- ★ Ligne de temps globale : objets versionnés et journal des effets donnent une annulation à l'échelle du système.
- ★ Inspecteur « pourquoi » : pointer n'importe quel pixel dit qui l'a dessiné, ce que ce composant peut atteindre et ce qu'il a fait.
- Accorder par le geste : choisir un fichier ou le glisser, c'est le donner ; aucune boîte de permission. Ancêtres : powerbox de CapDesk et de macOS.
- Automatisation par démonstration : les actions étant typées, ce que fait l'utilisateur s'enregistre en script rejouable.
- Notifications à budget : interrompre est une capacité, avec un quota ; l'agent trie le reste.
- Continuité : déplacer une surface en cours vers un autre appareil.
- Présence partagée : l'agent et l'utilisateur agissent sur la même surface, l'agent montre ce qu'il fait.
- Session invitée instantanée : prêter la machine avec un jeu de capacités réduit.
- Recherche sémantique locale sur tous les objets, avec leur provenance.

Ajouts du 14 novembre :

- Démarrage par instantané : à chaque mise à jour, on fige l'état des services déjà démarrés ; démarrer revient à mapper cette image.
- Interruptions alignées sur l'image : les périphériques sans urgence ne réveillent un cœur qu'en début de période.
- Boîte noire par tâche (voir « Panne et arrêt ») : sert aussi à rejouer et à expliquer ce qu'a fait l'agent.
- Catalogue d'interface par gabarit de surface : le même arbre rendu en bureau, téléphone, télévision, voiture, montre ou voix seule (voir « Déploiement et surfaces »).

## Déploiement et surfaces (proposé)

Ordre : (1) desktop de référence ; (1 bis, ouvert) image serveur sans écran, presque gratuite dès que le noyau a le disque et le réseau, et premier terrain pour vendre la reprise d'un noyau de cœur ; (2) portables ; (3) application compagnon sur Android, iOS, Linux, macOS et Windows ; (4) téléphones à bootloader libre ; (5) embarqué, dernière phase. Cet ordre n'était pas écrit dans ce document avant le 14 novembre 2026.

Ce que l'embarqué impose dès maintenant, à coût faible :

- **Noyau** : tout ce qui dépend de x86-64 derrière une couche d'architecture, pour porter vers ARM64 et RISC-V. Cible : processeurs avec MMU ; les microcontrôleurs sans MMU sont hors périmètre.
- **Wasm** : composants compilés à l'avance, sans compilateur sur l'appareil ; interpréteur en repli.
- **Configuration** : le système est un hash, donc une image embarquée est un autre hash, avec moins de services. Aucun service ne suppose un écran, un GPU, un clavier ou un agent local.
- **Interface** : le catalogue décrit le sens (bouton, champ, liste), pas la mise en page. Chaque surface a son gabarit de rendu.
- **Temps réel** : les contextes d'ordonnancement à budget et échéance conviennent déjà.
- **Mémoire** : porte « mémoire d'un processus vide » et taille de l'image minimale, à fixer.

## Matériel de référence

1. Desktop Intel + NVIDIA : en premier (décidé). Ni batterie ni Wi-Fi obligatoire. Le processeur n'a pas de GPU intégré : premiers pixels par le framebuffer du firmware (UEFI GOP), puis NVIDIA seul. Le chemin Intel se développe sur le Dell.
2. Portable Dell tout Intel : ensuite, quand la couche d'émulation est mûre. Demande le pilote i915 ou xe et l'interface DRM que Mesa attend.
3. Mac M5 : quand Asahi aura avancé.

## Méthode

Équipe : deux personnes et des agents IA. Deux pistes en parallèle, dans l'ordre proposé plus haut :

- **Noyau** : écrit depuis le modèle, vérifié par fuzzing différentiel contre seL4 en boîte noire. Limite : cet oracle ne couvre que la sémantique sur un cœur. Le modèle à un noyau par cœur, l'IOMMU et le chemin rapide demandent leurs propres tests.
- **Userland hébergé** : les mondes WIT implémentés sur Linux et macOS. C'est à la fois le SDK et le moyen de développer le compositeur, le stockage et l'agent sans attendre le noyau.

Suites de tests qui font foi : oracle différentiel (noyau), WPT (web), suite WASI (ABI), portes de latence (compositeur).

## Hors périmètre

- Machines virtuelles, compatibilité avec les applications Linux ou Windows, POSIX comme ABI.
- CUDA et DLSS.
- ABI native pour les applications, pour l'instant.
- 32 bits.
- Auto-hébergement du développement.

## Réponses proposées aux manques (14 novembre 2026, à valider)

**Système**

- Comptes : un utilisateur est une clé. Session ouverte par un code vérifié par le TPM ; biométrie plus tard. Aucun compte en ligne obligatoire. Pas de super-utilisateur : administrer, c'est détenir les capacités d'administration de l'appareil, remises au premier utilisateur. Plusieurs utilisateurs prévus dans la conception (zones par utilisateur) ; la v1 n'expose qu'un utilisateur et la session invitée.
- Clé perdue : clé de récupération remise à l'installation ; un autre appareil du cercle peut redonner la clé ; partage entre proches plus tard. Aucun séquestre chez nous.
- Sauvegarde : zones utilisateur et application, chiffrées avant l'envoi, vers un appareil du cercle, un disque externe ou un stockage objet de type S3. Incrémentale par construction (blobs désignés par hash). Restaurer : hash du système, liste des paquets, puis les objets. Changer de machine : appairage puis synchronisation.
- Installateur : l'image USB est le système en session éphémère ; installer, c'est écrire les partitions et copier les blobs. Double amorçage : cohabitation sur un disque dédié ou un espace libre, sans redimensionner les partitions d'un autre système en v1. Emplacement de secours : image minimale avec réseau, stockage, réinstallation, restauration, diagnostic.
- Firmwares : capsules UEFI ; source LVFS (de mémoire, à vérifier). Microcode : un blob du système, chargé par le noyau au démarrage.
- Pression mémoire : chaque processus a un budget mémoire. Ordre : vider les caches, compresser les pages des tâches de fond, figer en instantané les surfaces non visibles et libérer leur mémoire. On ne tue jamais sans instantané. Pas de mémoire d'échange en v1.
- Horloge : le noyau n'a qu'une horloge monotone. L'heure murale est un service (NTS), les fuseaux un blob.
- Langues : ICU4X pour les locales ; moteurs de saisie en composants Wasm sans réseau, branchés sur le protocole de saisie ; anglais et français en v1 ; format des messages à choisir (Fluent ou MessageFormat 2).
- Réglages : chaque service exporte ses réglages comme des actions avec schéma. L'écran des réglages est généré depuis le catalogue, et l'agent règle par le même chemin. Notifications : une surface du shell ; une notification porte des actions et une classe de priorité. Écran des droits : une requête sur l'arbre des capacités.
- Impression et numérisation : protocoles sans pilote (IPP Everywhere, eSCL), en composant, après la v1.

**Réseau**

- Pas de pare-feu séparé : le service réseau en tient lieu. Une application n'a aucun accès au réseau sans capacité, et la capacité porte sa portée (hôtes, ports, sortant ou entrant). Tout paquet entrant sans capacité d'écoute correspondante est jeté.
- Ouvrir un port : l'application demande dans son manifeste une capacité d'écoute (protocole, port, portée : machine, cercle d'appareils, réseau local ou internet). L'utilisateur l'accorde à l'installation ou au premier usage ; sur un serveur, elle est écrite dans la configuration. Portée internet : le service réseau demande la redirection au routeur (PCP, UPnP), ou mieux, expose le service par le transport par clé, sans aucun port ouvert. Révoquer la capacité ferme le port.
- Ce qui reste d'un pare-feu : limitation de débit dans le service réseau, et une politique d'administration qui borne les capacités qu'on peut accorder.
- DNS chiffré par défaut dans le service réseau ; mDNS local.
- VPN : un composant WireGuard qui reçoit une capacité réseau et en fournit une autre.
- Wi-Fi : reste ouvert (comparaison Linux et Fuchsia prévue).

**Médias**

- Codecs libres d'abord (AV1, VP9, Opus, FLAC). AV2 à suivre : spécification 1.0 publiée le 28 mai 2026, environ 30 % de débit en moins qu'AV1 ; pas de décodeur optimisé ni de matériel grand public trouvé (recherche du 14 novembre 2026). Rien à faire avant qu'un décodeur optimisé existe ; il entrera comme un composant de plus. H.264 et AAC par FFmpeg et Vulkan Video ; brevets à poser au juriste.
- Vidéo protégée : aucune voie vers Widevine aujourd'hui. Un navigateur indépendant attend encore sa licence (Zen), et rien trouvé sur EME dans Ladybird (recherche du 14 novembre 2026, sources communautaires). L'utilisateur signale que Zen a reçu sa licence le 14 novembre 2026 (vu sur X, non retrouvé par recherche) : si c'est confirmé, la voie existe pour un navigateur indépendant, à des conditions à connaître. Position d'ici là : limite assumée et affichée ; le contournement est la diffusion depuis un autre appareil. À réévaluer avec du volume.
- Polices : une famille système sous licence OFL, Noto pour la couverture des écritures et les emoji.

**Serveur**

- Exécute des composants `wasi:http` lancés à la requête ; logiciels natifs par POSIX en bibliothèque, plus tard.
- Administration : pas de shell root distant. L'outil `dodo` et l'agent passent par le transport par clé, avec des capacités d'administration déléguées. La configuration d'un serveur est un hash.
- Arguments : reprise d'un noyau de cœur, mise à jour du noyau sans redémarrage, démarrage en une seconde.

**Développeur**

- Terminal : une application. Shell : en porter un existant à données structurées (candidat Nushell, à vérifier), dont les commandes sont les actions ; pas de nouveau langage.
- Compiler sur DodOS : pas un but de la v1 ; on développe depuis Linux et macOS avec l'userland hébergé.
- Débogage : une capacité par composant (déjà noté). Traces : la boîte noire, exportée dans un format standard (Perfetto, à vérifier).

**Sécurité**

- Modèle de menace : une page, à l'étape 0. Attaquants : application malveillante, contenu web, injection de prompt, périphérique branché, voleur de la machine, réseau. Hors périmètre : firmware compromis, attaque physique avancée.
- Clés de signature : rôles TUF, racine hors ligne sur clés matérielles, seuil de deux clés sur trois (une par personne, une au coffre).
- Failles : fichier `SECURITY.md`, délai de divulgation de 90 jours, suivi des correctifs du noyau Linux à support long et de Ladybird.
- Canaux auxiliaires : la règle « un processus par éditeur » borne déjà le partage ; protections Spectre de Wasmtime actives ; horloge de précision réduite pour le contenu non fiable.
- Classe d'effet déclarée par l'application (faiblesse relevée) : la classe déclarée fixe les capacités remises pour l'appel. Une action `read` ne reçoit que des capacités en lecture et pas de réseau ; `reversible` ne reçoit que du stockage versionné ; seule `external` reçoit le réseau. Mentir sur la classe ne donne donc rien de plus.

**Workflow**

- Fusion : voie contrat (WIT, ABI, interfaces du noyau, portes), accord des deux humains ; voie fonction, un humain ; voie entretien, fusion automatique quand les contrôles passent.
- Fiches de décision : dans le dépôt commun de la documentation, puisque les décisions traversent les dépôts.
- Multithread : hypothèse de travail, les groupes de cœurs par messages (la reprise d'un noyau de cœur les favorise) ; le journal répliqué reste le point de comparaison à mesurer.

**Projet** (décisions de l'utilisateur ; recommandations)

- Qui achète : (1) licence commerciale pour les fabricants d'appareils et intégrateurs qui ne veulent pas de l'AGPL ; (2) support et licence côté serveur ; (3) services facultatifs (relais, sauvegarde, magasin) ; (4) une machine de référence. À trancher.
- Première démonstration publique, proposition : l'agent qui agit en sécurité sur des applications dans l'userland hébergé (étapes 1 à 3 de la piste hébergée), et le noyau qui démarre sous QEMU en passant l'oracle.
- Calendrier (proposé ; estimations sans mesure, à recalculer à chaque jalon d'après le débit réel des agents) :

  | Période | Piste hébergée | Piste noyau | Jalon |
  |---|---|---|---|
  | Décembre 2026 | Étape 0 : dépôt modèle, CI, `AGENTS.md`, modèle de menace | idem | Socle prêt |
  | T1 2027 | Runtime, outil `dodo`, surface | Démarrage, capacités, IPC, oracle (QEMU) | Porte IPC mesurée |
  | T2 2027 | Actions et agent | SMP, ordonnancement, mémoire, premier processus natif | Première démonstration publique, papier de position |
  | T3 2027 | Shell | IOMMU, pilotes NVMe, USB, réseau ; reprise d'un noyau de cœur | Démarrage sur le desktop de référence |
  | T4 2027 | Magasin de blobs, paquets signés | Image serveur sans écran | Première image serveur |
  | T1 2028 | | Cœur NVIDIA et NVK | Triangle Vulkan |
  | 2028 | Convergence : Ladybird, compositeur réel, portes de latence, audio, veille | | Alpha sur le desktop de référence |
  | 2029 | Portables, application compagnon | | Bêta |

- Budget en jetons (proposé) : une enveloppe mensuelle fixée par l'utilisateur, montant à donner. Répartition de départ : noyau 45 %, userland 25 %, revue et vérification 20 %, recherche 10 %. Plafond par tâche ; au-delà, l'agent s'arrête et remonte (règle déjà dans le harnais). Modèle le plus capable pour la voie contrat, le noyau et les revues ; modèle économique pour la recherche et l'entretien. Le coût par fusion est mesuré et publié dans la CI, et sert à recalculer le calendrier.
- Dépôt : `github.com/Vehicoule/dodOS` (public, créé le 13 novembre 2026, vide). Nom d'organisation : plus tard.
- Télémétrie : aucune par défaut ; un rapport de panne part sur accord, rapport par rapport.
- Accord de contribution : licence de contribution avec droit de relicencier, plutôt que cession. Texte et statut du code écrit par des agents : juriste.
- Nom (vérifié le 14 novembre 2026) : le nom `dodos` est pris sur GitHub par un compte utilisateur, il faudra un autre nom d'organisation ; `dodos.org` (2010) et `dodos.io` (2021) sont pris, `dod-os.org` est libre. Marque non vérifiée.

Restent ouverts, à voir ensemble : structure des jetons du design system, extension du catalogue, placement de la surface de l'agent, Wi-Fi, FRED sur le processeur de référence, relecture des « Contrôles par étape ».

## Questions ouvertes

- Nom DodOS : marque, domaine et organisation GitHub non vérifiés.
- Droit de créer du code exécutable pour le processus de contenu web : LibJS a un JIT actif par défaut depuis octobre 2026 (PR 12492 et 12613).
- Essai du shell : dessiner le catalogue avec gpui, puis Rune et LibWeb, et écrire le backend de fenêtre de gpui pour notre compositeur.
- A2UI : aucun SDK Rust officiel (TypeScript, Python, Dart, Swift, Kotlin). Écrire le compilateur Express en Rust à partir de la spécification et des suites de conformité, ou évaluer les crates communautaires.
- Coût de l'asynchrone des composants : environ 3,5 fois sur les appels synchrones dans Wasmtime, optimisation en cours en amont. À mesurer sur nos interfaces.
- Ladybird et méthodes d'entrée : la composition de texte existe dans LibWeb, branchée aujourd'hui par Qt. À brancher sur notre protocole.
- Version du noyau Linux pour les pilotes : à fixer quand la couche d'émulation démarre. Proposition : les sources de kernel.org, dernière version à support long, sans passer par une distribution, et sans bascule prévue vers une distribution ensuite. Aucun conflit avec Debian, qui ne sert que de source de correctifs pour les bibliothèques : pilotes et bibliothèques ne se lient jamais.
- Pile hôte Bluetooth : lire Sapphire et les profils de l'arbre Fuchsia.
- Performance GPU : à mesurer avec NVK sur la carte de la machine de référence.
- Mise à l'échelle et génération d'images au niveau du système : une surface 3D remettrait couleur, profondeur et vecteurs de mouvement à résolution et cadence réduites, et le service GPU ferait le reste. Les applets 3D de l'agent en seraient les premiers clients. ANR (Apex Compute) est candidat, on attend son code source et sa licence. ANR FG interpole entre deux images, donc il en retient une, mais ne coûte qu'environ 1 ms de GPU par image générée en 4K sur RTX 5090, 214 Mo de mémoire et 0,17 Mo de poids (chiffres de l'éditeur, non vérifiés par un tiers) ; version Metal native, donc portable. Le temps GPU libéré va au modèle local, dont la latence domine celle de l'agent. Proposition : activé par défaut pour les applets de l'agent et pour toute surface qui le demande, jamais imposé à une surface qui a demandé le chemin à faible latence.
- Distribution par un registre de conteneurs standard : à explorer. Point à régler : le registre identifie une couche par son SHA-256, nos blobs par leur racine de Merkle.
- Sécurité, proposition : la clé du disque est scellée dans le TPM (fTPM Intel du desktop) contre la clé de signature du système et non contre son hash, pour qu'une mise à jour ne casse pas le déverrouillage ; code de l'utilisateur protégé par l'anti-force-brute du TPM ; clé de récupération. Pas de mode développeur global : l'utilisateur inscrit une clé de développeur, et le débogage d'un composant est une capacité.
- Démarrage sécurisé, proposition : une seule image EFI signée (chargeur, noyau, image de démarrage). Sur nos machines, l'utilisateur inscrit notre clé ou la sienne dans le firmware. Pour les machines où ce n'est pas possible, un chargeur intermédiaire signé par Microsoft, plus tard.
- Décodage vidéo matériel : par Vulkan Video. NVK ne décode que le H.264 depuis Mesa 26.3 (H.265 bloqué, AV1 non confirmé), et dépend d'un correctif de nouveau à reporter dans notre fork. En attendant, décodage logiciel par FFmpeg.
- Ordonnancement du GPU : le service GPU arbitre seul le temps et la mémoire du GPU, avec les mêmes classes de latence que le processeur (compositeur et audio d'abord, inférence en tâche de fond, découpée en petits lots préemptibles). C'est ce qui tient la porte « rythme des images pendant une inférence ». Mécanisme de priorité des canaux NVIDIA à vérifier.
- Pile Wi-Fi : comparer la pile Linux (mac80211 compilé avec les pilotes) et celle de Fuchsia (MLME et SME en Rust, pilote iwlwifi déjà adapté, interfaces softmac et fullmac). Pas sur le chemin critique du desktop.
- Applications Electron : une couche de compatibilité (module `electron` et modules `node:` adossés à des capacités, rendu dans LibWeb) est possible pour les applications sans module natif. Non planifiée : la version web de l'application est le chemin par défaut.
- Étage optimisé de la compilation Wasm, à cadrer. Pistes à essayer : wasm2c puis LLVM (demande de décomposer le composant, de gérer les changements de pile de l'asynchrone, et LLVM sur la machine ou un service distant), inlineur de Cranelift entre composants, weval pour les langages interprétés.
- `core.wit` : annulation d'une action précise (`undo` ne désigne rien), grammaire du filtre de `query`, versions d'un objet, noms d'icônes sémantiques, deux interfaces de catalogue, interfaces audio et pilotes, gestion des surfaces par l'agent. Ajouter un cas à un variant casse l'ABI : le système devra servir chaque version publiée de `os:core`.
- Un noyau par cœur, points durs : un processus à plusieurs threads répartis sur plusieurs cœurs partage un espace d'adresses, donc ses tables de pages et ses capacités doivent rester cohérentes entre noyaux (messages, invalidation des TLB). seL4 retient lui aussi un multinoyau à partition statique comme voie vers le multicœur vérifié, et y déconseille l'IPC entre cœurs. Porte de surcoût à ajouter pour l'IPC entre cœurs. Cœurs P et E : la politique de placement reste en espace utilisateur.
- Structure hybride à étudier (proposé) : le découpage ne se fait pas par cœur mais par nature d'état. L'état propre à un cœur (IPC, ordonnancement, interruptions) reste local et sans verrou. L'état d'un processus étalé sur plusieurs cœurs (espace d'adresses, capacités) est répliqué par un journal partagé, technique de NrOS (OSDI 2021, un réplica par nœud NUMA). Précédent pour la cohérence d'un espace d'adresses entre noyaux : Popcorn Linux (ICDCS 2015). Précédent pour le remplacement d'un noyau cœur par cœur : Barrelfish/DC (OSDI 2014). La preuve du multinoyau de seL4 est prévue pour le 3e trimestre 2028.
- Threads Wasm : WASI 0.3.0 (11 juin 2026) n'a pas de threads. Threads coopératifs attendus dans une 0.3.x (Rust vise fin 2026, date incertaine) ; threads préemptifs plus tard, liés à `shared-everything-threads`, non implémenté dans Wasmtime. D'ici là, le parallélisme d'une application Wasm passe par plusieurs instances, ce qui convient à un noyau par cœur. Le natif (Ladybird, inférence) a besoin de vrais threads dès le début.
- Intel Software Defined Super Cores : brevet EP4579444A1 (déposé en 2023, publié en juillet 2025), plusieurs cœurs fusionnés pour un seul thread, vus comme un seul cœur par l'OS. Brevet, pas produit. À surveiller : si la fusion devient pilotable par l'OS, c'est une politique de plus pour l'espace utilisateur.
- Axes de recherche du noyau (proposé) : (1) provenance portée par l'IPC et appliquée par le noyau, pour borner ce qu'un agent peut faire d'un contenu non fiable ; (2) multinoyau à état de processus répliqué, vérifié ; (3) noyau écrit depuis un modèle par des agents, avec oracle différentiel et preuves bornées. (4) la tâche comme objet du noyau : un seul objet réunit les droits délégués, le budget de temps, l'étiquette de provenance et le journal d'une tâche de l'agent, révocable d'un coup ; (5) aucune page exécutable hors du service de compilation, appliqué par le noyau. Constat honnête : aujourd'hui les mécanismes du noyau sont tous empruntés (modèle de seL4, structure de Barrelfish) ; la nouveauté est dans la méthode, dans la combinaison et dans ces axes, dont aucun n'est encore conçu. Antériorité à lire avant toute revendication : AgentKernel (arXiv 2609.29647), ActPlane (arXiv 2606.25189), HongMeng (OSDI 2024).
- Antériorité des axes du noyau (étude déléguée à DeepSeek le 14 novembre 2026 ; sources lues en entier pour les travaux de 2026, résumés seulement pour les plus anciens ; non recoupée par nous). Le terrain est déjà occupé : un atelier AgenticOS existe (mars 2026, puis SOSP 2026). Verdicts :
  - À revendiquer, combinaison apparemment nouvelle : (a) la tâche comme objet du noyau, révoquée d'un coup. Chaque brique existe (seL4 MCS, Resource Containers, HiStar et Asbestos, Cinder, jobs de Fuchsia) ; le plus proche est Agate (AgenticOS '26), sans étiquette de flux ni journal d'effets. Défense : un modèle formel de la révocation. (b) Provenance dans les messages IPC, classe d'effet, et confirmation humaine comme seule levée d'étiquette. Le plus proche : ActPlane (eBPF sous Linux) et CaMeL (hors noyau). (c) Groupes de cœurs dynamiques : le multinoyau en grappes de von Tessin (2012) est notre idée en statique, Barrelfish/DC l'est sans partage ; seul le regroupement dynamique est libre, et il casse la structure de preuve qu'apporte la partition statique.
  - Méthode (noyau écrit par agents, oracle seL4, Kani et Verus) : aucun précédent trouvé, mais difficile à défendre : l'oracle ne voit que la surface de l'ABI.
  - À ne pas présenter comme nouveau : tâches spéculatives (« Fork, Explore, Commit », arXiv 2602.08199, et « Externalization Barriers », AgenticOS '26, déjà publiés avec du code) ; aucune page exécutable hors service de compilation (iOS et Singularity) ; capacités à budget (seL4 MCS et Cinder) ; explication de l'autorité (une requête sur l'arbre de dérivation) ; noyau par type de cœur (Barrelfish/DC et Popcorn). Ils restent utiles au produit.
  - Faiblesses à traiter : tout devient vite « non fiable » et l'utilisateur confirme tout ; une étiquette ne suit pas l'influence du contenu sur la décision du modèle ; une application peut mentir sur la classe d'effet de ses actions ; un effet externe ne s'annule pas ; un budget copié devient un compteur partagé.
- Pistes issues de la recherche récente (seconde étude DeepSeek du 14 novembre 2026, non recoupée ; chiffres à relire dans les articles) :
  - Retenues (accord de l'utilisateur, à concevoir) : (a) ordonnancement ancré sur l'écran : pas de tic, le rafraîchissement ouvre chaque période, et les soumissions GPU entrent dans le même graphe d'échéances que le processeur ; aucun noyau trouvé qui le fasse. (b) Contrats de latence portés par les capacités, avec admission au moment de l'octroi et un modèle que l'agent peut interroger ; par budgets mesurés, le pire cas calculé sur du Wasm étant irréaliste. (c) Capacités typées par WIT : le compilateur émet le manifeste, `own` et `borrow` deviennent dérivation et atténuation ; c'est déjà notre conception, et elle ne semble pas publiée. (d) Manifeste de pilote déduit de traces (plages MMIO, fenêtres DMA par anneau, interruptions), la relecture portant sur la différence à chaque mise à jour ; limite : les chemins rares (veille, erreurs) manquent aux traces. (e) Mémoire à la CortenMM (SOSP 2025) : la table de pages comme seule représentation, partie concurrente minuscule et vérifiée ; annoncé 1,2 à 26 fois plus rapide que Linux. (f) Copie mémoire comme service du noyau avec échéance (Copier, SOSP 2025). (g) Interruptions utilisateur (xUI, ASPLOS 2025 ; Aeolia, SOSP 2025) pour livrer un événement à un composant sans entrer dans le noyau. (h) Flux (types de raffinement pour Rust) comme outil de preuve : TickTock (SOSP 2025) a vérifié l'isolation de Tock et trouvé sept bugs.
  - Matériel : FRED (nouvelle livraison d'événements x86, pile choisie par niveau) convient à un noyau sans pile par thread, et aucun article ne l'évalue ; à vérifier : notre processeur de référence l'a-t-il ? Le chemin classique par IDT reste obligatoire. APX (32 registres généraux, annoncé pour Nova Lake) : prévoir un format de message IPC en registres plus large. LAM à ne pas utiliser (attaque SLAM, désactivé dans Linux). CET à exiger. La distinction entre types de cœurs est à traiter comme durable (décidé) : Arm, Apple, Intel et AMD y convergent ; la rumeur d'un « cœur unifié » d'Intel vers 2028 ne change pas ce choix.
  - Écartées : espace d'adresses unique entre composants par clés de protection (contredit notre règle d'un processus par éditeur, et les clés du mode utilisateur sont modifiables par le code) ; modèle de langage dans le noyau.
  - Cœurs hétérogènes, retenu : la classe de cœur fait partie du contrat d'une capacité d'ordonnancement (chemin de l'image sur cœurs rapides, travail de fond sur cœurs économes), et un noyau par cœur autorise un binaire réglé par type de cœur.
  - Concurrent direct : Agate (AgenticOS '26), micronoyau à capacités pour agents, AArch64, sans évaluation ni preuve. WALI (EuroSys 2025) : Wasm au-dessus des appels système, à citer pour dire ce qu'on supprime.
- Structure dynamique (proposé) : le nombre de cœurs actifs et leur attribution suivent la charge. Barrelfish/DC ajoute, retire et remplace un cœur à chaud (retrait en 0,0008 ms contre 2 542 ms pour Linux 3.13, chiffres des auteurs). Le réplica d'un processus n'existe que sur les cœurs où il a un thread. Variante à comparer au journal répliqué : un noyau par groupe de cœurs, le groupe d'un processus multithread partageant un seul noyau avec un verrou court, et changeant de taille selon la charge (précédents : Popcorn, un noyau par cœur ou par groupe ; NrOS, par nœud NUMA).
- Emprunts à étudier, de mémoire, à vérifier dans les articles : HongMeng (classes d'isolation différenciées, services regroupables dans un même espace d'adresses sans changer leur code, pas d'état tenu en double) ; sDDF de LionsOS (files sans verrou à un producteur et un consommateur en mémoire partagée, pilotes à un thread) ; seL4 MCS (le temps comme capacité, pour nos classes de latence) ; Barrelfish (cœurs traités comme des périphériques, état du noyau externalisé en capacités) ; NrOS (bibliothèque de réplication, table de pages vérifiée) ; Asterinas (socle `unsafe` minimal et audité).
- Publications : papier de position tôt (OS sûr pour un agent : classes d'effet, provenance, confirmations), puis papiers de mesure une fois les portes en place (oracle différentiel et développement par agents, réutilisation des pilotes Linux sans VM, Wasm comme seule ABI). Les portes fournissent les chiffres. Le papier de position n'est pas en terrain vierge : AgentKernel (arXiv 2609.29647, septembre 2026) propose déjà des étiquettes de provenance dans un « OS pour agent » ; le lire avant d'écrire. Papier d'architecture : thèse défendable « l'avantage du monolithique s'érode », pas « il va disparaître ».
- Design system : voir la section. Structure des jetons à décider, extension du catalogue pour les applications natives.
- Workflow : qui des deux humains fusionne quoi ; fiches de décision dans chaque dépôt ou dans un dépôt commun. La CI proposée a été jugée insuffisante une première fois : la liste « Contrôles par étape » attend une relecture.
- Lecture du code des noyaux dont on s'inspire (décidé) : les agents lisent le code de tous les noyaux ouverts, seL4 compris. Nous ne reprenons de seL4 que le minimalisme, les tests et les bancs, dans d'autres langages et une autre architecture. Une seule règle : aucune traduction fichier par fichier ni copie, et l'origine d'une idée reprise est citée. Sources permissives vérifiées : Barrelfish (MIT), cœur NVIDIA (MIT) ; Asterinas est en MPL-2.0, noyau seL4 en GPLv2. Pas de séparation en deux agents : coût jugé disproportionné. Avis juridique avant une version commerciale.
- Preuve formelle du noyau : hors de portée en entier (Zig n'a pas d'outil de preuve). Piste partielle : Verus sur la logique Rust (capacités, cycle de vie des objets). Précédent : Atmosphere, micronoyau Rust de 6 000 lignes vérifié avec Verus en moins de 2,5 années-personne (SOSP 2025), avec un verrou global. Kani (vérification bornée, sans annotations, sait traiter le code `unsafe`) en complément, dans la CI : absence de panique, de débordement et d'erreur mémoire.
- Arbre d'interface : écrire le catalogue DodOS au format A2UI. Placement et taille de la surface de l'agent.
- Accord de cession des contributeurs, nécessaire à la double licence.
- Pile réseau : faire notre propre extraction du cœur de Netstack3 depuis l'arbre Fuchsia, et juger l'écart avec l'amont.

## État de vérification

Vérifié le 13 novembre 2026 contre des sources primaires, par cinq audits délégués et des contrôles directs dans les dépôts :

- Ladybird : architecture des processus, dépendances, crates Rust, JIT, accessibilité, méthodes d'entrée, WebGPU, politique de contribution (commit c8b525e).
- Wasm : WASI 0.3, Wasmtime et ses compilateurs, état de chaque langage, uutils, brush, A2UI 1.0, llama.cpp 1.0.
- GPU et interface : portage NVIDIA de Haiku et son fork de Mesa, gpui, gpui-kit, Rune, wgpu, performance de NVK.
- Système : piles Bluetooth, mot d'éveil par le processeur de signal, uACPI, sDDF, DFv2, Netstack3, noyaux Linux à support long.
- Harnais : articles de GitHub et de Microsoft, conventions `AGENTS.md` et skills, offres gratuites.
- Performance et divers : banc libsodium 2026, Segue, inlineur de Cranelift, weval, SpaceWasm, chiffres IPC de seL4, ANR (chiffres de l'éditeur seulement), Vulkan Video dans NVK, pile Wi-Fi de Fuchsia, distribution par `wkg`, pilotes en VM de LionsOS.

Vérifié le 14 novembre 2026, par recherche web (résumés et pages officielles, articles non lus en entier) : multinoyau de seL4 et date de sa preuve, NrOS, Barrelfish/DC, Popcorn Linux, constat de HongMeng, LionsOS (chiffres des auteurs), brevet Intel des super cœurs, calendrier des threads de WASI, existence d'AgentKernel et d'ActPlane.

Encore de mémoire, à vérifier avant de s'y appuyer :

- Détail des emprunts aux micronoyaux récents (HongMeng, sDDF, seL4 MCS, Asterinas) : articles à lire en entier.
- Gain réel du noyau par cœur pour les cœurs P et E, et coût comparé du journal répliqué et du noyau par groupe de cœurs : rien de mesuré.
- Conférences et dates pour les publications.

- Faisabilité de la frontière Zig et Rust, et du noyau événementiel sans pile par thread.
- SQLite avec un VFS maison en mode WAL.
- Bibliothèque standard de Rust branchée sur mlibc (précédent supposé : Managarm).
- Adaptateur WASI 0.1 pour Zig et Swift, et état d'Odin.
- État actuel de Genode DDE Linux, pile Wi-Fi de FreeBSD, rôle exact de Nova.
- Emprunts à Plan 9, Genode, Horizon, SepOS et Minix 3 : inspirations de conception, non relues.
- Réalisme des portes de latence et de surcoût : cibles à calibrer par la mesure.
- Plans matériels et priorité des canaux exposés par le cœur NVIDIA sans sa couche Linux.
- TPM et démarrage sécurisé : mécanismes connus, non relus. Chargeur signé par Microsoft pour un OS non Linux : non vérifié.
- Variants WIT : un cas ajouté casse la compatibilité.
- Décodage vidéo matériel dans Ladybird : état inconnu.
- Noyau livré par Debian 14 : notes de version incohérentes.

- 14 novembre 2026 (suite) : absence de banc de démarrage seL4, cherchée sur le web, pas dans le dépôt sel4bench. RFC-14 de seL4 (seuils de budget) : lue par résumé de recherche, état de fusion non vérifié. Scheduler activations, crash-only, Wi-Fi Aware sur iOS, Quick Share et AirDrop, firmware GPU : de mémoire.

## Emprunts

| Source | Ce qu'on prend |
|---|---|
| seL4 | Mémoire fournie par l'espace utilisateur, contextes d'ordonnancement, révocation par arbre de dérivation |
| Fuchsia | Objets mémoire, routage déclaratif des capacités, modèle de blobfs, TUF, emplacements A/B/R |
| Plan 9 | Un seul protocole pour tout, transparence réseau, agent gardien des secrets |
| Genode | Parent-enfant récursif, échange de ressources, compositeur de confiance minuscule |
| Horizon | Manifeste signé par processus, limites de ressources fixes |
| Barrelfish | Un noyau par cœur |
| SepOS | Service de clés à interface étroite, classes de protection des données |
| Minix 3 | Redémarrage automatique des pilotes |
| Nix | Machine décrite par un fichier déclaratif, générations |
| Ubuntu Core | Assertions signées, canaux, déploiement progressif, récupération |
| bootc | Un registre de conteneurs standard comme moyen de distribution : ses couches sont déjà des blobs adressés par hash |
| Debian | Ses correctifs de portage hors de Linux (Hurd), pour nos dépendances sur mlibc |
| ART | Compilation à l'installation puis optimisation en arrière-plan |
| A2UI | Format d'interface émis par l'agent, mécanisme de catalogue |
