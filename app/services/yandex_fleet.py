# -*- coding: utf-8 -*-
# app/services/yandex_fleet.py

class YandexFleetProvider:
    async def sync(self, *args, **kwargs):
        return {"status": "ok"}

yandex_provider = YandexFleetProvider()
