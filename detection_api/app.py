import json
import asyncio  # For running tasks in parallel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Literal, Union
import uvicorn  # ASGI server implementation for FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from starlette.websockets import WebSocketState

from contextualizer import Contextualizer
from propaganda_detection import OpenAITextClassificationPropagandaInference

# Initialize the FastAPI application
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Request(BaseModel):
    """
    Pydantic model for the request payload, specifying the structure of the request for analysis.
    """
    model_name: str  # The OpenAI model to use
    text: str  # The article text to analyze
    contextualize: Union[Literal["Auto"], bool] = False  # Allows "Auto", True, or False


async def process_entry(entry, contextualizer, auto=False):
    """
    Helper function to process a single entry for contextualization in parallel.
    """
    if auto:
        seems_factual = await contextualizer.seems_factual(entry["location"])
        if seems_factual:
            entry["contextualize"] = (await contextualizer.process_statement(entry["location"]))["output"]
        else:
            entry["contextualize"] = "Not factual"
    else:
        entry["contextualize"] = (await contextualizer.process_statement(entry["location"]))["output"]
    return entry


async def contextualize(request, analysis_results):
    if request.contextualize == True or request.contextualize == "Auto":
        contextualizer = Contextualizer(model_name=request.model_name)
        tasks = []  # List to store asyncio tasks

        for category, entries in analysis_results.items():
            for entry in entries:
                if request.contextualize == "Auto":
                    tasks.append(process_entry(entry, contextualizer, auto=True))
                else:
                    tasks.append(process_entry(entry, contextualizer))

        # Run all tasks concurrently
        await asyncio.gather(*tasks)
        return True
    return False


def detect_propaganda(request):
    inference_class = OpenAITextClassificationPropagandaInference(model_name=request.model_name)
    analysis_results = inference_class.analyze_article(input_text=request.text)
    return analysis_results


@app.websocket("/ws/analyze_propaganda")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket connection to analyze articles for propaganda and broadcast results in real time.
    """
    await websocket.accept()

    try:
        while True:
            # Receive the request data from WebSocket
            data = await websocket.receive_text()
            request = Request.parse_raw(data)

            # Step 1: Perform propaganda analysis
            analysis_results = detect_propaganda(request)

            # Step 2: Send the raw propaganda analysis back to the client
            status = analysis_results.pop("status")
            if status == "error":
                await websocket.send_text(json.dumps({
                    "type": "propaganda_detection",
                    "status": "error",
                    "message": analysis_results["error"]
                }))
                return
            else:
                await websocket.send_text(json.dumps(analysis_results))

            # Step 3: If contextualization is enabled, process it and send the updated entries
            try:
                was_contextualized = await contextualize(request, analysis_results)
                if was_contextualized:
                    # Step 4: Send the contextualized results after processing
                    await websocket.send_text(json.dumps(analysis_results))
            except Exception as e:
                logging.error(f"An error occurred during contextualization: {e}")
                await websocket.send_text(json.dumps({
                    "type": "contextualization",
                    "status": "error",
                    "message": str(e)
                }))
    except WebSocketDisconnect:
        logging.info("Client disconnected")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()


# Entry point for running the application
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
