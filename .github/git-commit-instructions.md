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

| Shortcode | Use for |
|-----------|--------|
| `:sparkles:` | New feature |
| `:bug:` | Bug fix |
| `:ambulance:` | Critical hotfix |
| `:adhesive_bandage:` | Small non-critical fix |
| `:recycle:` | Refactor |
| `:art:` | Structure/format only |
| `:zap:` | Performance |
| `:memo:` | Documentation |
| `:bulb:` | Comments only |
| `:white_check_mark:` | Add or update tests |
| `:rotating_light:` | Linter/compiler warnings |
| `:fire:` | Remove code or files |
| `:heavy_plus_sign:` | Add dependency |
| `:heavy_minus_sign:` | Remove dependency |
| `:arrow_up:` | Upgrade dependency |
| `:arrow_down:` | Downgrade dependency |
| `:construction:` | WIP |
| `:rewind:` | Revert |
