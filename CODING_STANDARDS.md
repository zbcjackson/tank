# Coding Standards

This document defines coding standards, design principles, and code quality guidelines for the Tank Voice Assistant project.

## Code Simplification Principles

### Remove Unnecessary Abstraction Layers

- **Avoid wrapping functionality that already provides what you need**
  - If a library/component already handles threshold comparison, don't add another layer
  - If a component returns the exact result you need, use it directly instead of converting
  - Avoid creating wrapper methods that only convert formats without adding logic
  - Example: If `VADIterator` already does threshold comparison and returns boolean-like results, don't wrap it with a method that converts to float and back to boolean

### Eliminate Redundant Logic

- **Don't duplicate functionality that's already handled**
  - If a dependency already performs a check/comparison, don't repeat it
  - Pass configuration parameters directly to dependencies that support them
  - Example: Pass `speech_threshold` directly to `VADIterator` instead of doing threshold comparison yourself

### Direct Usage Over Wrappers

- **Prefer direct usage when the abstraction adds no value**
  - If an intermediate method only converts formats without adding logic, consider removing it
  - Keep code paths simple and direct
  - Example: Call `VADIterator` directly in `_process_chunk` instead of through `_infer_speech_prob` that only converts return values