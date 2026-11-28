# Changelog

## [0.2.0](https://github.com/Sette/telegram-exec-notifier/compare/v0.1.0...v0.2.0) (2026-11-28)


### Features

* **notifier:** ✨ add telegram notifier client and cli ([3a2cd50](https://github.com/Sette/telegram-exec-notifier/commit/3a2cd504de6b2f96acdd0e05bf200126ee146ae9))
* **permissions:** ✨ ask claude permissions on telegram with auto-approve folder mode ([4f270b3](https://github.com/Sette/telegram-exec-notifier/commit/4f270b3a8f6e89ff96839226c90182f02f6d8503))
* **security:** ✨ load bot credentials from a systemd encrypted credential ([ff854f7](https://github.com/Sette/telegram-exec-notifier/commit/ff854f7f63cbae8e35148b6d39a4098fdb46088b))
* **security:** ✨ load settings from systemd encrypted credential and hide token from agents ([0a6452f](https://github.com/Sette/telegram-exec-notifier/commit/0a6452fffc2827ede4a75a0ac8dc60e9c813a8ab))
* **server:** ✨ add local notification and command receiver service ([e76fced](https://github.com/Sette/telegram-exec-notifier/commit/e76fcedf7f248b26f730f6c24147f14ccfed9bb9))
* **server:** ✨ route plain text to claude and add session resume commands ([84ae8c5](https://github.com/Sette/telegram-exec-notifier/commit/84ae8c5cade8dfb8109c98e1461ca43d0cd9130a))
* **server:** ✨ stream claude replies to telegram with progress heartbeats ([a819081](https://github.com/Sette/telegram-exec-notifier/commit/a819081b21166223617d11ad2bdb36d4e8cbedc0))
* **server:** ✨ stream claude replies to telegram with progress heartbeats ([583bb45](https://github.com/Sette/telegram-exec-notifier/commit/583bb452c5847e7bc5588a2405f58145ebcdae50))


### Bug Fixes

* **server:** 🐛 render agent markdown as telegram html ([1f51439](https://github.com/Sette/telegram-exec-notifier/commit/1f514394069200d3d43f1d9ea03ad18ba2bb2ae1))
* **server:** 🐛 render agent markdown as telegram html ([18acbda](https://github.com/Sette/telegram-exec-notifier/commit/18acbda57488e06317879a8a857725a4df3f9dd2))


### Documentation

* **readme:** 📝 add project documentation ([35c28c0](https://github.com/Sette/telegram-exec-notifier/commit/35c28c0ebd89f206d51726e8021306ab7040f1a2))
* **readme:** 📝 document default claude routing and session commands ([4c291eb](https://github.com/Sette/telegram-exec-notifier/commit/4c291ebd4917cd1c8efec9fe5f16c5fd4b59ecfc))
* **readme:** 📝 document encrypted credentials ([5af034e](https://github.com/Sette/telegram-exec-notifier/commit/5af034ef6c514eabfcdeeab60c72359b5dec00e1))
* **readme:** 📝 document pypi install, docker and release process ([68b25a5](https://github.com/Sette/telegram-exec-notifier/commit/68b25a553967d7a3b3f37982011f2b30dcf28044))
* **readme:** 📝 document streamed claude replies and new settings ([7eae3b3](https://github.com/Sette/telegram-exec-notifier/commit/7eae3b3ab77c661d3e41cebae9e1134cd1424253))
* **readme:** 📝 document telegram permission approval and auto folder mode ([d53337c](https://github.com/Sette/telegram-exec-notifier/commit/d53337c544dfb3cfd5335db0480fe14490b4adcc))
* **readme:** 📝 mention env example ([3c2fcb9](https://github.com/Sette/telegram-exec-notifier/commit/3c2fcb998c709d1777f1d907fc7ce9fd85b8f8a9))
* **readme:** 📝 update service path notes ([ced2519](https://github.com/Sette/telegram-exec-notifier/commit/ced251921b3f72d2301414a2c79778e4ee7fd657))
