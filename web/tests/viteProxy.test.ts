// @vitest-environment node
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createConnection } from 'node:net';
import { connect } from 'node:tls';
import { createServer as createViteServer } from 'vite';
import { expect, test, vi } from 'vitest';
import config from '../vite.config';

test('unexpected proxy failures remain visible', () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
  try {
    const error = Object.assign(new Error('connect ECONNREFUSED'), { code: 'ECONNREFUSED' });
    config.customLogger?.error('ws proxy error:', { error });
    expect(errors).toHaveBeenCalled();
    errors.mockClear();
    config.customLogger?.error('http proxy error:', {
      error: Object.assign(new Error('read ECONNRESET'), { code: 'ECONNRESET' }),
    });
    expect(errors).toHaveBeenCalled();
  } finally {
    errors.mockRestore();
  }
});

test.each(['fin', 'reset'])('WebSocket client %s closes the proxy without errors', async (mode) => {
  const backend = createServer();
  let markBackendClosed: () => void = () => {};
  const backendClosed = new Promise<void>((resolve) => { markBackendClosed = resolve; });
  backend.on('upgrade', (request, socket) => {
    const key = request.headers['sec-websocket-key'];
    const accept = createHash('sha1')
      .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
      .digest('base64');
    socket.write(
      'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n' +
      `Connection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`,
    );
    // Keep producing frames as the browser disconnects, as audio does.
    const timer = setInterval(() => socket.write(Buffer.from([0x81, 0x01, 0x78])), 1);
    socket.on('close', () => { clearInterval(timer); markBackendClosed(); });
    socket.on('end', () => socket.destroy());
    socket.on('error', () => socket.destroy());
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');
  const backendAddress = backend.address();
  if (backendAddress === null || typeof backendAddress === 'string') throw new Error('no backend port');
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
  const ws = config.server?.proxy?.['/ws'];
  if (!ws || typeof ws === 'string') throw new Error('missing WS proxy');
  const cacheDir = await mkdtemp(join(tmpdir(), 'tank-vite-proxy-'));
  const vite = await createViteServer({
    configFile: false,
    cacheDir,
    plugins: [config.plugins?.[0]],
    customLogger: config.customLogger,
    optimizeDeps: { noDiscovery: true, include: [] },
    server: {
      host: '127.0.0.1', port: 0,
      proxy: { '/ws': { ...ws, target: `ws://127.0.0.1:${backendAddress.port}` } },
    },
  });
  let client: ReturnType<typeof connect> | undefined;
  let transport: ReturnType<typeof createConnection> | undefined;
  try {
    await vite.listen();
    const address = vite.httpServer?.address();
    if (!address || typeof address === 'string') throw new Error('no proxy port');
    transport = createConnection({ host: '127.0.0.1', port: address.port });
    client = connect({ socket: transport, rejectUnauthorized: false });
    client.on('error', () => {});
    await once(client, 'secureConnect');
    client.write(
      'GET /ws/test HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n' +
      'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n' +
      'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n',
    );
    const [handshake] = await once(client, 'data');
    expect(handshake.toString()).toContain('101 Switching Protocols');
    const closed = once(client, 'close');
    if (mode === 'reset') transport.resetAndDestroy();
    else client.end();
    await closed;
    await backendClosed;
    await new Promise<void>((resolve) => setImmediate(resolve));
    expect(errors).not.toHaveBeenCalled();
  } finally {
    client?.destroy();
    transport?.destroy();
    await vite.close();
    await new Promise<void>((resolve) => backend.close(() => resolve()));
    await rm(cacheDir, { recursive: true, force: true });
    errors.mockRestore();
  }
});
