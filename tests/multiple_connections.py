import asyncio
import websockets
import json

async def connect_to_websocket(client_id):
    async with websockets.connect("ws://127.0.0.1:8000/ws/analyze_propaganda", ping_interval=None) as websocket:
        # Define the request data
        request_data = {
            "model_name": "gpt-4o",  # Example model
            "text": "An apparent Israeli airstrike on Monday morning hit central Beirut for the first time since the 2006 war, according to reporters on the ground in the city. A week-long bombing campaign on Lebanon has decimated the leadership of Hezbollah and sent hundreds of thousands of civilians fleeing north. The strike in the capital's Kola district killed three leaders of the Popular Front for the Liberation of Palestine (PFLP), the organization has confirmed.",
            "contextualize": True
        }

        # Send the request data
        await websocket.send(json.dumps(request_data))
        print(f"Client {client_id}: Request sent.")

        # Keep receiving responses indefinitely
        while True:
            try:
                response = await websocket.recv()
                print(f"Client {client_id}: Streamed response received:\n{response}")
            except websockets.ConnectionClosedError:
                print(f"Client {client_id}: Connection closed.")
                break
            except Exception as e:
                print(f"Client {client_id}: An error occurred: {e}")
                break

async def simulate_multiple_clients():
    tasks = []
    for i in range(5):  # Simulate 5 clients
        tasks.append(connect_to_websocket(i+1))

    await asyncio.gather(*tasks)

asyncio.run(simulate_multiple_clients())
