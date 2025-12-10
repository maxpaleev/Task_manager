from fastapi import FastAPI
from .endpoints import register_endpoints

app = FastAPI()

register_endpoints(app)