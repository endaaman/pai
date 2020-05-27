import json
import asyncio
import websockets

WS_HOST = 'localhost:8081'


class WS:
    def __init__(self):
        super().__init__()
        self.ws = None

    def is_active(self):
        # return ws and ws.sock and ws.sock.connected
        return self.ws and self.ws.open

    async def close(self):
        # return ws and ws.sock and ws.sock.connected
        if not self.is_active():
            return
        await self.ws.close()
        self.ws = None

    async def connect(self):
        try:
            self.ws = await websockets.connect(f'ws://{WS_HOST}')
        except Exception as e:
            print('Failed to connect', e)
            self.ws = None
            return
        print('Connected')
        return True

    async def acquire_status(self):
        try:
            await self.ws.send('status')
            data = await self.ws.recv()
        except json.JSONDecodeError:
            print(f'PARSE ERROR: {data}')
            await self.ws.close()
            return None
        # except Exception as e:
        #     print('ERROR WHEN SENDING OR RECEIVING', e)
        #     return None
        return json.loads(data)
