import asyncio
import json
import logging
import uuid
from typing import Literal, Union, Optional

import logfire
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.websockets import WebSocketState

import dependencies
from database import AnalysisResult
from database.repo import Repo
from llm.contextualizer import Contextualizer
from llm.propaganda_detection import OpenAITextClassificationPropagandaInference

# Configure logging
logfire.configure()
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logfire.LogfireLoggingHandler()])

# Initialize the FastAPI application
app = FastAPI()
logfire.instrument_fastapi(app)
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
async def process_entry(entry, contextualizer: Contextualizer, auto=False):
    entry["contextualize_status"] = "success"

    try:
        if auto:
            seems_factual = await contextualizer.seems_factual(entry["location"])
            if seems_factual:
                result = await contextualizer.process_statement(entry["location"])
            else:
                entry["contextualize"] = "Not factual"
                entry["contextualize_status"] = "success"
                return
        else:
            result = await contextualizer.process_statement(entry["location"])

        if result["status"] == "success":
            entry["contextualize_status"] = "success"
            entry["contextualize"] = result["output"]
        else:
            entry["contextualize_status"] = "error"
            entry["contextualize_error"] = result["error"]
    except Exception as e:
        logging.error(f"An error occurred during contextualization: {e}", exc_info=True)
        entry["contextualize_status"] = "error"
        entry["contextualize_error"] = f"Error: {str(e)}"

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
    analysis_results = await inference_class.analyze_article(request.text)
    return analysis_results


async def handle_request(data, websocket, repo):
    request = Request.parse_raw(data)
    with logfire.span("handle_request user_id={user_id} model_name={model_name} contextualize={contextualize}",
                      user_id=request.user_id,
                      model_name=request.model_name,
                      contextualize=request.contextualize):
        logging.info(f"Received data: {data}")

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
            await websocket.close()
            return
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
                "message": f"An error occurred during contextualization: {str(e)}"
            }))

        # Step 4: Close the WebSocket connection after all responses are sent
        await websocket.close()

        # Step 5: Save the full response to the database
        analysis_result = AnalysisResult(
            user_id=user_id,
            model_name=request.model_name,
            text=request.text,
            contextualize=request.contextualize,
            result=json.dumps(analysis_results)
        )
        repo.create(analysis_result)


@app.websocket("/ws/analyze_propaganda")
async def websocket_endpoint(websocket: WebSocket,
                             repo: Repo = Depends(dependencies.repo)):
    await websocket.accept()
    logging.info("WebSocket connection accepted")
    try:
        data = await websocket.receive_text()
        await handle_request(data, websocket, repo)
    except WebSocketDisconnect:
        logging.info("Client disconnected")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()


# Entry point for running the application
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
