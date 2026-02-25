# Git Commit Instructions

Use **gitmoji shortcode text** instead of conventional commit types (e.g. `feat:`, `fix:`). Start the subject line with a shortcode (e.g. `:sparkles:`), **not** the raw emoji character.

## Format

```
:shortcode: <imperative summary>

[optional body]
```

- **Subject**: One line, ~50 chars or less. Use imperative mood (“Add …”, “Fix …”, not “Added …”, “Fixes …”).
- **Body** (optional): Wrap at 72 chars. Explain what and why, not how.

## Examples

```text
:sparkles: Add Edge TTS output and SpeakerHandler
:bug: Fix circular import in runtime
:recycle: Move AudioOutputRequest to core.events
:memo: Update ARCHITECTURE for TTS ABC
:white_check_mark: Add test for TTSEngine ABC instantiation
:fire: Remove deprecated audio/tts.py
:arrow_up: Bump pydub and add audioop-lts
```

## Gitmoji reference (use the shortcode in commits)

### Features & Fixes

| Shortcode | Use for |
|-----------|--------|
| `:sparkles:` | New feature |
| `:bug:` | Bug fix |
| `:ambulance:` | Critical hotfix |
| `:adhesive_bandage:` | Simple fix for non-critical issue |
| `:boom:` | Introduce breaking changes |
| `:pencil2:` | Fix typos |
| `:goal_net:` | Catch errors |
| `:necktie:` | Add or update business logic |

### Code Quality & Refactoring

| Shortcode | Use for |
|-----------|--------|
| `:recycle:` | Refactor code |
| `:art:` | Improve code structure or formatting |
| `:zap:` | Boost performance |
| `:fire:` | Remove code or files |
| `:coffin:` | Remove dead code |
| `:wastebasket:` | Deprecate code needing cleanup |
| `:poop:` | Write code needing improvement |
| `:building_construction:` | Make architectural changes |
| `:label:` | Add or update types |

### Documentation & Comments

| Shortcode | Use for |
|-----------|--------|
| `:memo:` | Add or update documentation |
| `:bulb:` | Add or update code comments |
| `:speech_balloon:` | Add or update text and literals |
| `:page_facing_up:` | Add or update license |

### Testing

| Shortcode | Use for |
|-----------|--------|
| `:white_check_mark:` | Add, update, or pass tests |
| `:test_tube:` | Add a failing test |
| `:clown_face:` | Mock things |
| `:camera_flash:` | Add or update snapshots |

### Dependencies

| Shortcode | Use for |
|-----------|--------|
| `:heavy_plus_sign:` | Add a dependency |
| `:heavy_minus_sign:` | Remove a dependency |
| `:arrow_up:` | Upgrade dependencies |
| `:arrow_down:` | Downgrade dependencies |
| `:pushpin:` | Pin dependencies to specific versions |

### CI/CD & DevOps

| Shortcode | Use for |
|-----------|--------|
| `:construction_worker:` | Add or update CI build system |
| `:green_heart:` | Fix CI build |
| `:rocket:` | Deploy changes |
| `:rotating_light:` | Fix compiler or linter warnings |
| `:wrench:` | Add or update configuration files |
| `:hammer:` | Add or update development scripts |
| `:bookmark:` | Release or version tags |
| `:bricks:` | Infrastructure-related changes |
| `:stethoscope:` | Add or update healthcheck |

### Security & Auth

| Shortcode | Use for |
|-----------|--------|
| `:lock:` | Fix security or privacy issues |
| `:closed_lock_with_key:` | Add or update secrets |
| `:passport_control:` | Work on authorization and permissions |
| `:safety_vest:` | Add or update validation code |

### UI & UX

| Shortcode | Use for |
|-----------|--------|
| `:lipstick:` | Update UI and style files |
| `:dizzy:` | Add or update animations and transitions |
| `:wheelchair:` | Improve accessibility |
| `:children_crossing:` | Improve user experience |
| `:iphone:` | Work on responsive design |
| `:mag:` | Improve SEO |

### Data & Logging

| Shortcode | Use for |
|-----------|--------|
| `:card_file_box:` | Make database-related changes |
| `:seedling:` | Add or update seed files |
| `:loud_sound:` | Add or update logs |
| `:mute:` | Remove logs |
| `:chart_with_upwards_trend:` | Add or update analytics |
| `:monocle_face:` | Data exploration or inspection |

### Assets & Resources

| Shortcode | Use for |
|-----------|--------|
| `:bento:` | Add or update assets |
| `:truck:` | Move or rename resources |
| `:package:` | Add or update compiled files or packages |
| `:globe_with_meridians:` | Internationalization and localization |

### Project Management

| Shortcode | Use for |
|-----------|--------|
| `:tada:` | Begin a project |
| `:construction:` | Work in progress |
| `:rewind:` | Revert changes |
| `:twisted_rightwards_arrows:` | Merge branches |
| `:triangular_flag_on_post:` | Add, update, or remove feature flags |
| `:see_no_evil:` | Add or update .gitignore |
| `:busts_in_silhouette:` | Add or update contributors |

### Specialized

| Shortcode | Use for |
|-----------|--------|
| `:alien:` | Update code for external API changes |
| `:thread:` | Add or update multithreading or concurrency code |
| `:technologist:` | Improve developer experience |
| `:alembic:` | Perform experiments |
| `:egg:` | Add or update an easter egg |
| `:money_with_wings:` | Add sponsorships or money infrastructure |
| `:airplane:` | Improve offline support |
| `:t-rex:` | Add backwards compatibility |
| `:beers:` | Write code drunkenly |
