from fastapi import FastAPI

from server.Bot.tg_bot import send_message

def register_endpoints(app: FastAPI):
    @app.get("/")
    async def root():
        return {"message": "Hello World"}

    @app.get("/items/{item_id}")
    async def read_item(item_id: int, q: str = None):
        await send_message(item_id, q)
        return {"item_id": item_id, "q": q}
