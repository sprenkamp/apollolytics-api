import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Literal, Union, Optional
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
import logging
from starlette.websockets import WebSocketState
import uuid  

from llm.contextualizer import Contextualizer
from llm.propaganda_detection import OpenAITextClassificationPropagandaInference
from database.postgres import save_request_to_db


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize the FastAPI application
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the request model
class Request(BaseModel):
    user_id: Optional[str] = None  # Add user_id field
    model_name: str
    text: str
    contextualize: Union[Literal["Auto"], bool] = False

# Define a function to process each entry in the analysis results
async def process_entry(entry, contextualizer, auto=False):
    if auto:
        seems_factual = await contextualizer.seems_factual(entry["location"])
        if seems_factual:
            entry["contextualize"] = (await contextualizer.process_statement(entry["location"]))["output"]
        else:
            entry["contextualize"] = "Not factual"
    else:
        entry["contextualize"] = (await contextualizer.process_statement(entry["location"]))["output"]
    return entry

# Define a function to contextualize the analysis results
async def contextualize(request, analysis_results):
    if request.contextualize in [True, "Auto"]:
        contextualizer = Contextualizer(model_name=request.model_name)
        tasks = []

        for category, entries in analysis_results.items():
            for entry in entries:
                if request.contextualize == "Auto":
                    tasks.append(process_entry(entry, contextualizer, auto=True))
                else:
                    tasks.append(process_entry(entry, contextualizer))

        await asyncio.gather(*tasks)
        return True
    return False

# Define the main route for the FastAPI application
async def detect_propaganda_async(request):
    inference_class = OpenAITextClassificationPropagandaInference(model_name=request.model_name)
    analysis_results = await asyncio.to_thread(inference_class.analyze_article, input_text=request.text)
    return analysis_results

@app.websocket("/ws/analyze_propaganda")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket connection accepted")
    try:
        while True:
            data = await websocket.receive_text()
            logging.info(f"Received data: {data}")
            request = Request.parse_raw(data)

            # Generate or retrieve user_id
            if request.user_id is None:
                user_id = str(uuid.uuid4())
                logging.info(f"Generated new user_id: {user_id}")
            else:
                user_id = request.user_id
                logging.info(f"Using existing user_id: {user_id}")

            # Step 1: Perform propaganda analysis
            analysis_results = await detect_propaganda_async(request)
            logging.info(f"Analysis results: {analysis_results}")
            
            # Step 2: Send the raw propaganda analysis back to the client
            status = analysis_results.pop("status", "error")
            if status == "error":
                await websocket.send_text(json.dumps({
                    "user_id": user_id,
                    "type": "propaganda_detection",
                    "status": "error",
                    "message": analysis_results.get("error", "Unknown error")
                }))
                continue  # Continue to allow the client to send more messages
            else:
                await websocket.send_text(json.dumps({
                    "user_id": user_id,
                    "type": "propaganda_detection",
                    "status": "success",
                    "data": analysis_results
                }))

            # Step 3: If contextualization is enabled, process it and send the updated entries
            try:
                was_contextualized = await contextualize(request, analysis_results)
                if was_contextualized:
                    await websocket.send_text(json.dumps({
                        "user_id": user_id,
                        "type": "contextualization",
                        "status": "success",
                        "data": analysis_results
                    }))
            except Exception as e:
                logging.error(f"An error occurred during contextualization: {e}", exc_info=True)
                await websocket.send_text(json.dumps({
                    "user_id": user_id,
                    "type": "contextualization",
                    "status": "error",
                    "message": str(e)
                }))

            # Step 4: Save the full response to the database
            await asyncio.to_thread(
                save_request_to_db,
                user_id=user_id,
                model_name=request.model_name,
                text=request.text,
                contextualize=request.contextualize,
                result=analysis_results
            )

    except WebSocketDisconnect:
        logging.info("Client disconnected")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()

# Entry point for running the application
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
