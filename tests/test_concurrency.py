import asyncio
import aiohttp
import json
import random
import sys

BASE_URL = "http://localhost:8000"

async def update_contact(session, contact_id, name):
    url = f"{BASE_URL}/contacts/{contact_id}"
    data = {
        "id": contact_id,
        "name": name,
        "phone": "+1234567890",
        "group": "Test Group",
        "created_at": "2024-01-01T00:00:00"
    }
    try:
        async with session.put(url, json=data) as response:
            return await response.json()
    except Exception as e:
        print(f"Error updating contact {contact_id}: {e}")
        return None

async def main():
    # First, ensure we have some contacts
    async with aiohttp.ClientSession() as session:
        # Create a test contact if needed (assuming ID 1 exists or we can create it)
        # For this test, we'll try to update contact ID 1 repeatedly
        
        print("Starting concurrency test...")
        
        tasks = []
        for i in range(10):
            name = f"Concurrent Update {i}"
            tasks.append(update_contact(session, 1, name))
            
        results = await asyncio.gather(*tasks)
        
        print(f"Completed {len(results)} updates.")
        
        # Verify the final state
        async with session.get(f"{BASE_URL}/contacts/") as response:
            contacts = await response.json()
            print(f"Total contacts: {len(contacts)}")
            contact_1 = next((c for c in contacts if c['id'] == 1), None)
            if contact_1:
                print(f"Contact 1 Name: {contact_1['name']}")
            else:
                print("Contact 1 not found!")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
