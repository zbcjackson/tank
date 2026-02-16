"""Simple CLI tool to test the Voice Assistant WebSocket API."""

import asyncio
import websockets
import json
import sys

async def test_client(session_id: str):
    uri = f"ws://localhost:8000/ws/{session_id}"
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected to {uri}")
            
            async def receive_messages():
                try:
                    async for message in websocket:
                        if isinstance(message, str):
                            data = json.loads(message)
                            if data["type"] == "transcript":
                                print(f"User: {data['content']}", end="", flush=True)
                            elif data["type"] == "text":
                                print(f"
Assistant: {data['content']}", end="", flush=True)
                            elif data["type"] == "signal":
                                print(f"
[Signal] {data['content']}")
                            elif data["type"] == "update":
                                print(f"
[Update] {data['metadata']}")
                        else:
                            print(f"
[Audio] Received {len(message)} bytes")
                except websockets.exceptions.ConnectionClosed:
                    print("
Connection closed")

            receive_task = asyncio.create_task(receive_messages())

            print("Commands: 'text <msg>', 'interrupt', 'quit'")
            while True:
                cmd_input = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
                if cmd_input.startswith("text "):
                    text = cmd_input[5:]
                    msg = {
                        "type": "input",
                        "content": text,
                        "session_id": session_id
                    }
                    await websocket.send(json.dumps(msg))
                elif cmd_input == "interrupt":
                    msg = {
                        "type": "signal",
                        "content": "interrupt",
                        "session_id": session_id
                    }
                    await websocket.send(json.dumps(msg))
                elif cmd_input == "quit":
                    break
                else:
                    print("Unknown command")

            receive_task.cancel()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "demo_session"
    asyncio.run(test_client(sid))
