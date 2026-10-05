import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, UploadFile, File
from ai.agents.vision.crew import run_vision_agent
from fastapi.responses import JSONResponse
from ai.agents.vision.schemas import VisionSchema
from typing import AsyncGenerator, List

from settings import Config


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator:
    yield


router = APIRouter(tags=['vision'], lifespan=lifespan)


@router.post('/vision')
async def vision(prompt: str, image: UploadFile = File()) -> VisionSchema:
    return run_vision_agent(prompt=prompt, image=image)


@router.get('/health')
async def health() -> JSONResponse:
    return JSONResponse({'status': 'healthy'})


app = FastAPI(version=Config.API_VERSION)
app.include_router(router=router)

if __name__ == '__main__':
    uvicorn.run(app=app, host='0.0.0.0', port=3333, use_colors=True)
