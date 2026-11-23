# Changelog

All notable changes to this project are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/);
each section corresponds to a git version tag (which is also the release
published to PyPI). Entries are commit subjects and PR titles, verbatim.

## [Unreleased]


## [0.0.61] - 2026-11-23

- Derive __version__ from package metadata ([#84](https://github.com/addaix/aix/pull/84))

## [0.0.60] - 2026-11-23

- chat/complete: claude-cli/<model> backend over claude -p, no API key ([#81](https://github.com/addaix/aix/pull/81)) ([#83](https://github.com/addaix/aix/pull/83))

## [0.0.59] - 2026-11-23

- credentials: local Ollama models need no API key (closes [#80](https://github.com/addaix/aix/pull/80)) ([#82](https://github.com/addaix/aix/pull/82))

## [0.0.58] - 2026-11-22

- Type coverage pass: return annotations on public methods [skip publish] ([#77](https://github.com/addaix/aix/pull/77))
- chore: stop ignoring the whole docs/ folder [skip publish] ([#76](https://github.com/addaix/aix/pull/76))

### Docs

- docs: README note on when to use DSPy instead of prompt_func ([#79](https://github.com/addaix/aix/pull/79))
- docs: skip-mark key/network README blocks; register the source in the OpenRouterSource example [skip publish] ([#78](https://github.com/addaix/aix/pull/78))

## [0.0.57] - 2026-11-22

### Added

- feat(prompts): prompt_func exposes an inspectable keyword-only signature ([#74](https://github.com/addaix/aix/pull/74))

## [0.0.56] - 2026-11-22

### Fixed

- fix(credentials): infer the provider of common model ids offline ([#75](https://github.com/addaix/aix/pull/75))

## [0.0.55] - 2026-11-06

- Restore the image tests overwritten in [#67](https://github.com/addaix/aix/pull/67); default model openai/gpt-image-1.5 ([#68](https://github.com/addaix/aix/pull/68))

## [0.0.54] - 2026-11-06

- Image generation: send response_format only when given; default to gpt-image-1.5 (OpenAI retired dall-e-3) ([#67](https://github.com/addaix/aix/pull/67))

## [0.0.53] - 2026-10-13

- test(sampling): cover Samples accessors and n-refusal memo edges ([#65](https://github.com/addaix/aix/pull/65))

## [0.0.52] - 2026-10-13

- sample(): remember per model that n is refused ([#61](https://github.com/addaix/aix/pull/61)); image edit/variation models in config ([#62](https://github.com/addaix/aix/pull/62))

## [0.0.51] - 2026-10-13

### Fixed

- fix(config): using() holds its override in a ContextVar ([#60](https://github.com/addaix/aix/pull/60))

## [0.0.50] - 2026-10-12

### Changed

- refactor(vision): shared request builder; preflight resolves aliases ([#59](https://github.com/addaix/aix/pull/59))

## [0.0.49] - 2026-10-12

### Fixed

- fix(sample): fall back when the provider refuses server-side n ([#58](https://github.com/addaix/aix/pull/58))

## [0.0.48] - 2026-10-12

### Fixed

- fix: import aix no longer imports the optional oa package ([#57](https://github.com/addaix/aix/pull/57))

## [0.0.47] - 2026-10-12

### Added

- feat: aix.supports(model, param); documented seed and determinism ([#53](https://github.com/addaix/aix/pull/53))

## [0.0.46] - 2026-10-12

### Added

- feat: response_schema= for provider-enforced, validated structured output ([#52](https://github.com/addaix/aix/pull/52))

## [0.0.45] - 2026-10-12

### Added

- feat: sample() primitive; constrained_answer(n=k) runs concurrently ([#51](https://github.com/addaix/aix/pull/51))

## [0.0.44] - 2026-10-12

### Added

- feat: complete() returns the whole response (all n choices, usage, finish reasons) ([#50](https://github.com/addaix/aix/pull/50))

## [0.0.43] - 2026-09-22

### Fixed

- fix: constrained_answer rejected valid members of a mixed options list ([#49](https://github.com/addaix/aix/pull/49))

## [0.0.42] - 2026-09-22

- Add .claude/CLAUDE.md index ([#48](https://github.com/addaix/aix/pull/48))

## [0.0.41] - 2026-09-22

### Fixed

- fix: constrained_answer coercion neither truncates nor over-rejects; eager on_error check ([#47](https://github.com/addaix/aix/pull/47))

## [0.0.40] - 2026-09-22

### Fixed

- fix: enforce constrained_answer's constraint; type batch failure slots ([#46](https://github.com/addaix/aix/pull/46))

## [0.0.39] - 2026-08-07

- ci: re-trigger the CI+publish the 2026-08-06 Actions outage swallowed

### Fixed

- fix: resolve litellm on first call, not at import — `import aix` no longer reaches the network ([#39](https://github.com/addaix/aix/pull/39))

## [0.0.38] - 2026-06-25

### Added

- feat(vision): compare_images — structured two-image likeness check ([#37](https://github.com/addaix/aix/pull/37))

## [0.0.37] - 2026-06-23

### Added

- feat(audio): optional engine= delegation to scribed (multi-engine ASR)

## [0.0.36] - 2026-06-18

### Added

- feat(vision): image→text (describe_image) over LiteLLM ([#35](https://github.com/addaix/aix/pull/35))

## [0.0.35] - 2026-06-17

- chore(wads): repo-improvement pass ([#34](https://github.com/addaix/aix/pull/34))

## [0.0.34] - 2026-06-17

### Added

- feat: support oa-style {var:default} default-aware template dialect ([#32](https://github.com/thorwhalen/aix/pull/32))

## [0.0.33] - 2026-06-16

- prompt_func: add egress + name (oa.prompt_function parity) ([#30](https://github.com/thorwhalen/aix/pull/30))

## [0.0.32] - 2026-06-05

- Unified, discoverable credential resolution + preflight ([#24](https://github.com/thorwhalen/aix/pull/24)) ([#28](https://github.com/thorwhalen/aix/pull/28))

## [0.0.31] - 2026-06-04

- chore: gitignore .claude/handoffs/
- Refresh default models + add semantic alias resolution ([#27](https://github.com/thorwhalen/aix/pull/27))

## [0.0.29] - 2026-06-04

- Add central config (SSOT) for per-function model defaults ([#26](https://github.com/thorwhalen/aix/pull/26))

## [0.0.28] - 2026-06-02

- Fix CI: patch shadowed submodules via sys.modules ([#21](https://github.com/thorwhalen/aix/pull/21))
- Minimize dependencies + finish wads CI migration ([#20](https://github.com/thorwhalen/aix/pull/20))

## [0.0.27] - 2026-05-27

- ci: switch to wads reusable workflow stub
- ci: bump action pins in legacy main.yml + tests.yml workflows
- ci: migrate old CI to uv (wads-migrate ci-to-uv)

### Fixed

- fix(ci): wire OPENAI_API_KEY via [tool.wads.ci.env.test_envvars]

## [0.0.26] - 2026-05-16

- Add batching, persistent caching, and segment truncation to embeddings ([#18](https://github.com/thorwhalen/aix/pull/18))

## [0.0.25] - 2026-02-05

- style: Simplify formatting in pyproject.toml for consistency
- Refactor code structure for improved readability and maintainability
- Incorporate changes from claude/develop-aix-package-01JcT9HKUTrDGQapErZR3x5h
- delete docsrc
- misc docs
- chores
- 0.0.24:
- Add new dependencies to setup.cfg
- more in aix_contexts_wip

### Added

- feat: Implement constrained_answer as a flexible replacement for oa.constrained_answer
- feat: Implement AI Model Management Module

### Changed

- refactor: remove legacy ML tools
- refactor: Rename get_app_data_folder to get_app_config_folder
- refactor: Organize imports and enhance utility functions in util.py; add new Jupyter notebook for model data exploration

### Fixed

- fix: Add GITHUB_TOKEN to CI environment variables for improved access
- fix: Update assertions in TestChatSession and TestModelStore for accuracy

## [0.0.23] - 2025-03-26

### Added

- feat: extract_urls

## [0.0.22] - 2025-03-05

### Docs

- docs: add reference link to bytes_to_markdown function docstring

## [0.0.21] - 2025-03-04

- Maintenance only (all commits in this range were CI version bumps / housekeeping).

## [0.0.20] - 2025-03-04

### Added

- feat: update import statements to use bytes_store_to_markdown_store function
- feat: rename convert_to_markdown and convert_files_to_markdown functions to bytes_to_markdown and bytes_store_to_markdown_store

## [0.0.19] - 2025-03-04

### Added

- feat: convert_to_markdown and convert_files_to_markdown

## [0.0.18] - 2025-02-27

### Added

- feat: add aggregate_store function for processing and aggregating text files

## [0.0.17] - 2025-02-26

### Added

- feat: started a stores module

## [0.0.16] - 2025-01-30

### Added

- feat: notebook_to_markdown

## [0.0.15] - 2025-01-29

### Added

- feat: PackageCodeContexts

### Fixed

- fix: doctest

## [0.0.14] - 2025-01-18

### Added

- feat: enhance save_to_file_and_return_file with key parameter for flexible file naming

## [0.0.13] - 2025-01-17

### Added

- feat: save_to_file_and_return_file

## [0.0.12] - 2025-01-15

### Added

- feat: refactor code aggregation functions and add local package support

## [0.0.11] - 2025-01-15

### Added

- feat: aggregate_code

## [0.0.10] - 2025-01-14

- Update ci.yml

## [0.0.9] - 2025-01-14

- Update ci.yml
- Update ci.yml

## [0.0.8] - 2025-01-12

### Added

- feat: implement article download functionality with context management

## [0.0.7] - 2025-01-08

- Update ci.yml
- Update setup.cfg
- Update setup.cfg
- new ci
- 0.0.4: facades for ai chat
- 0.0.3:
- add docs/* to .gitignore
- None: fix: *.ipynb linguist-documentation in .gitattributes
- gitignore
- added a space to --line-length=88 to trigger non-trivial git status
- Replaced --line-length=79 with --line-length=88
- "auto_ci_stuff"
- Update main.yml
- Changed name of secrete token
- Create main.yml
- 0.0.2:

### Added

- feat: get_llm_leaderboards

### Fixed

- fix: add tests
- fix: string DeprecationWarning
- fix: .com --> .com.com
