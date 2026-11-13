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
- Continuité entre appareils (synchronisation locale, pair à pair) : jamais discutée.
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
- Structure dynamique (proposé) : le nombre de cœurs actifs et leur attribution suivent la charge. Barrelfish/DC ajoute, retire et remplace un cœur à chaud (retrait en 0,0008 ms contre 2 542 ms pour Linux 3.13, chiffres des auteurs). Le réplica d'un processus n'existe que sur les cœurs où il a un thread. Variante à comparer au journal répliqué : un noyau par groupe de cœurs, le groupe d'un processus multithread partageant un seul noyau avec un verrou court, et changeant de taille selon la charge (précédents : Popcorn, un noyau par cœur ou par groupe ; NrOS, par nœud NUMA).
- Emprunts à étudier, de mémoire, à vérifier dans les articles : HongMeng (classes d'isolation différenciées, services regroupables dans un même espace d'adresses sans changer leur code, pas d'état tenu en double) ; sDDF de LionsOS (files sans verrou à un producteur et un consommateur en mémoire partagée, pilotes à un thread) ; seL4 MCS (le temps comme capacité, pour nos classes de latence) ; Barrelfish (cœurs traités comme des périphériques, état du noyau externalisé en capacités) ; NrOS (bibliothèque de réplication, table de pages vérifiée) ; Asterinas (socle `unsafe` minimal et audité).
- Publications : papier de position tôt (OS sûr pour un agent : classes d'effet, provenance, confirmations), puis papiers de mesure une fois les portes en place (oracle différentiel et développement par agents, réutilisation des pilotes Linux sans VM, Wasm comme seule ABI). Les portes fournissent les chiffres. Le papier de position n'est pas en terrain vierge : AgentKernel (arXiv 2609.29647, septembre 2026) propose déjà des étiquettes de provenance dans un « OS pour agent » ; le lire avant d'écrire. Papier d'architecture : thèse défendable « l'avantage du monolithique s'érode », pas « il va disparaître ».
- Design system : voir la section. Structure des jetons à décider, extension du catalogue pour les applications natives.
- Workflow : qui des deux humains fusionne quoi ; fiches de décision dans chaque dépôt ou dans un dépôt commun. La CI proposée a été jugée insuffisante une première fois : la liste « Contrôles par étape » attend une relecture.
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
