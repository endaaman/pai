import websocket

WS_HOST = 'localhost:8081'


class WS:
    def __init__(self):
        super().__init__()
        self.ws = None

    def is_active(self):
        # return ws and ws.sock and ws.sock.connected
        return self.ws and self.ws.connected

    def close(self):
        # return ws and ws.sock and ws.sock.connected
        if not self.ws:
            return
        if self.ws.connected:
            self.ws.close()
        self.ws = None

    def connect(self):
        try:
            self.ws = websocket.create_connection(f'ws://{WS_HOST}/status')
        except Exception as e:
            print('Failed to connect', e)
            self.ws = None
            return
        print('Connected')

    def acquire_status(self, *args):
        try:
            self.ws.send('status')
            return self.ws.recv()
        except Exception as e:
            print('ERROR WHEN SENDING OR RECEIVING', e)
        return False
