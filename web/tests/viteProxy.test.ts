// @vitest-environment node
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { createServer } from 'node:http';
import { connect } from 'node:tls';
import { createLogger, createServer as createViteServer } from 'vite';
import { expect, test, vi } from 'vitest';
import config from '../vite.config';

test('WebSocket client disconnect closes the proxy without write-after-FIN errors', async () => {
  const backend = createServer();
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
    socket.on('close', () => clearInterval(timer));
    socket.on('end', () => socket.destroy());
    socket.on('error', () => socket.destroy());
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');
  const backendAddress = backend.address();
  if (backendAddress === null || typeof backendAddress === 'string') throw new Error('no backend port');
  const logger = createLogger();
  const errors = vi.spyOn(logger, 'error');
  const ws = config.server?.proxy?.['/ws'];
  if (!ws || typeof ws === 'string') throw new Error('missing WS proxy');
  const vite = await createViteServer({
    configFile: false,
    plugins: [config.plugins?.[0]],
    customLogger: logger,
    server: {
      host: '127.0.0.1', port: 0,
      proxy: { '/ws': { ...ws, target: `ws://127.0.0.1:${backendAddress.port}` } },
    },
  });
  let client: ReturnType<typeof connect> | undefined;
  try {
    await vite.listen();
    const address = vite.httpServer?.address();
    if (!address || typeof address === 'string') throw new Error('no proxy port');
    client = connect({ host: '127.0.0.1', port: address.port, rejectUnauthorized: false });
    await once(client, 'secureConnect');
    client.write(
      'GET /ws/test HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n' +
      'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n' +
      'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n',
    );
    const [handshake] = await once(client, 'data');
    expect(handshake.toString()).toContain('101 Switching Protocols');
    const closed = once(client, 'close');
    client.end();
    await closed;
    expect(errors).not.toHaveBeenCalled();
  } finally {
    client?.destroy();
    await vite.close();
    await new Promise<void>((resolve) => backend.close(() => resolve()));
  }
});
