# Author Dunin Ilya.
""" Module description """

import aiofiles
from aiohttp import web, WSMsgType, WSCloseCode
from aio_pika import connect_robust, Message
from asyncio import get_event_loop
from json import loads, dumps
from json import decoder
from logging import getLogger
from pathlib import Path

from utils import setup_logger
from config import RMQ_CHANNEL_NAME, RMQ_CONN_STR

BASE_DIR = Path(__file__).parent.absolute()
logger = getLogger(__name__)
setup_logger(logger)


class Application(web.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.aio_loop = get_event_loop()

        self.ws_connections = {}
        self.setup_routes()
        self.pub_channel = None

        self.on_startup.append(self.start_rmq)

        self.on_cleanup.append(self.stop_rmp)
        self.on_shutdown.append(self.cleanup_ws_conns)

    def setup_routes(self):
        """ Setup Application routes """
        self.add_routes(
            [web.get('/ws', self.ws_handler),
             web.get('/chat', self.js_chat)],
        )

    async def js_chat(self, request):
        async with aiofiles.open(BASE_DIR / "index.html", mode="r") as f:
            page = await f.read()

        return web.Response(text=page, content_type='text/html', charset='utf-8')

    async def cleanup_ws_conns(self, app):
        """ Clean up all connection, send GOING AWAY signal for all connected clients

        :param app:
        :return:
        """
        logger.info('Clean up connections...')
        for uid, ws in self.ws_connections.items():
            logger.info(f'Cleanup connection for user: {uid}')
            await ws.close(
                code=WSCloseCode.GOING_AWAY,
                message=b'Server shutdown.',
            )

    async def ws_handler(self, request):
        """ Process all incoming WS connections """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        user_id = request.query.get('token')

        if user_id:
            logger.info(f'Add connection for user: {user_id}')
            self.ws_connections[user_id] = ws
        else:
            logger.warning('User connected without token...')
            return web.HTTPBadRequest()

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
                else:
                    try:
                        data = loads(msg.data)
                        await self.publish_message(data.get('id'), data.get('msg'))
                    except decoder.JSONDecodeError:
                        logger.warning('Incorrect message')
            elif msg.type == WSMsgType.ERROR:
                logger.error('ws connection closed with exception %s', ws.exception())

        logger.error(f'Connection for user: {user_id} closed! Remove connection')
        self.ws_connections.pop(user_id)
        return ws

    async def listener(self, app):
        """ RMQ listener """
        connection = await connect_robust(RMQ_CONN_STR, loop=self.aio_loop)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=100)
        queue = await channel.declare_queue(RMQ_CHANNEL_NAME, auto_delete=False)
        await queue.consume(self.process_message)
        return connection

    async def publish_message(self, uid, message):
        """ Add message to RMQ """
        msg = {'id': str(uid), 'msg': message}
        connection = await connect_robust(RMQ_CONN_STR, loop=self.aio_loop)
        async with connection:
            channel = await connection.channel()
            await channel.default_exchange.publish(
                Message(
                    body=dumps(msg).encode()
                ),
                routing_key=RMQ_CHANNEL_NAME
            )

    async def process_message(self, message):
        """ Process incoming RMQ messages """
        async with message.process():
            data = loads(message.body)
            user_id = data.get('id')
            if not user_id:
                logger.warning('Message without user id')
                return

            ws = self.ws_connections.get(user_id)
            if ws is None:
                logger.warning(f'User {user_id} not connected')
                return
            else:
                logger.info('Send message')
                msg = str(data.get('msg'))
                await ws.send_str(msg)

    async def start_rmq(self, app):
        """ Start RMQ listener """
        logger.info('Init Rabbit MQ')
        self['rmq'] = self.aio_loop.create_task(self.listener(self))

    async def stop_rmp(self, app):
        """ Stop RMQ listener """
        logger.info('Stop Rabbit MQ')
        self['rmq'].cancel()
        await self['rmq']


if __name__ == '__main__':
    web.run_app(app=Application(), port=8080)

