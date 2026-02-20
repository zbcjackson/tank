# Web Frontend Testing Guidelines

This document provides testing guidelines for the Tank Web Frontend.

## Framework

- **Unit/Integration**: Vitest + React Testing Library (add when needed)
- **E2E**: Playwright (add when needed)
- **Location**: `tests/` (to be created alongside test files)

> Note: The project currently has no test setup. When adding tests, install:
> ```bash
> npm install -D vitest @testing-library/react @testing-library/user-event jsdom
> ```
> Add to `vite.config.ts`:
> ```ts
> test: { environment: 'jsdom', globals: true }
> ```

## What to Test

### Custom Hooks (`hooks/`)

Hooks contain the most complex logic and are the highest-value test targets.

```ts
import { renderHook, act } from '@testing-library/react';
import { useAssistant } from '../hooks/useAssistant';

// Mock WebSocket and AudioProcessor
vi.mock('../services/websocket');
vi.mock('../services/audio');

test('signal:ready sets connectionStatus to connected', () => {
  const { result } = renderHook(() => useAssistant('test-session'));
  // Simulate server sending signal message
  act(() => {
    mockOnMessage({ type: 'signal', content: 'ready', ... });
  });
  expect(result.current.connectionStatus).toBe('connected');
});
```

### Services (`services/`)

Test pure logic (audio conversion, message parsing) without real WebSocket/AudioContext.

```ts
test('Int16 PCM is correctly converted to Float32', () => {
  const int16 = new Int16Array([0, 16384, -16384, 32767]);
  const float32 = convertInt16ToFloat32(int16);
  expect(float32[0]).toBeCloseTo(0);
  expect(float32[1]).toBeCloseTo(0.5, 1);
  expect(float32[2]).toBeCloseTo(-0.5, 1);
});
```

### Components

Test behavior visible to the user, not implementation details.

```tsx
import { render, screen } from '@testing-library/react';

test('ChatMode renders assistant message', () => {
  const messages = [{ id: '1', role: 'assistant', type: 'text', content: 'Hello!' }];
  render(<ChatMode messages={messages} isAssistantTyping={false} onSendMessage={() => {}} />);
  expect(screen.getByText('Hello!')).toBeInTheDocument();
});
```

## Mocking

### WebSocket

```ts
vi.mock('../services/websocket', () => ({
  VoiceAssistantClient: vi.fn().mockImplementation(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    sendAudio: vi.fn(),
    sendMessage: vi.fn(),
  })),
}));
```

### Web Audio API

```ts
// In test setup file
global.AudioContext = vi.fn().mockImplementation(() => ({
  createBuffer: vi.fn(),
  createBufferSource: vi.fn(() => ({ connect: vi.fn(), start: vi.fn() })),
  destination: {},
  currentTime: 0,
}));
```

### getUserMedia

```ts
Object.defineProperty(global.navigator, 'mediaDevices', {
  value: { getUserMedia: vi.fn().mockResolvedValue(new MediaStream()) },
});
```

## Key Principles

- **Test behavior, not implementation** — assert on what the user sees or what state is exposed, not internal variables
- **Mock all browser APIs** (WebSocket, AudioContext, getUserMedia) — they don't exist in jsdom
- **Mock services in hook tests** — test the hook's logic, not the service's
- **Keep tests fast** — no real network, no real audio

## Performance Targets

- Unit tests: < 100ms each
- Full suite: < 10 seconds

## Test Quality Checklist

- [ ] WebSocket, AudioContext, getUserMedia are mocked
- [ ] Tests assert on observable output (rendered text, state values)
- [ ] No access to component internals or private service methods
- [ ] Tests pass without a real backend
- [ ] Each test is independent (no shared mutable state between tests)
