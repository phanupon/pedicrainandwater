"""
WebSocket consumers for real-time flood alerts.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger('flood_alert')


class AlertConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer สำหรับส่งการแจ้งเตือนแบบ real-time."""

    async def connect(self):
        await self.channel_layer.group_add('alerts', self.channel_name)
        await self.accept()
        logger.info(f'WebSocket client connected: {self.channel_name}')
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': 'เชื่อมต่อระบบแจ้งเตือนน้ำท่วมสำเร็จ',
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('alerts', self.channel_name)
        logger.info(f'WebSocket client disconnected: {self.channel_name}')

    async def receive(self, text_data):
        """รับข้อความจาก client (เช่น subscribe จังหวัดที่ต้องการ)."""
        try:
            data = json.loads(text_data)
            if data.get('action') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError:
            pass

    async def send_alert(self, event):
        """ส่งการแจ้งเตือนไปยัง client."""
        await self.send(text_data=json.dumps({
            'type': 'alert',
            'data': event['alert'],
        }))
