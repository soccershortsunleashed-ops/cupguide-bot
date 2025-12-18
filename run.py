import uvicorn

if __name__ == "__main__":
    print("Starting Telegram Monitor...")
    print("Open http://127.0.0.1:8000 in your browser")
    uvicorn.run(
        "app.main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        # Убираем лимит запросов (None = без лимита)
        limit_max_requests=None,
        timeout_keep_alive=60
    )
