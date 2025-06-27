from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# routers
from routers import ingredients
from routers import ingredientbatches

app = FastAPI(title="Ingredients Service")

# include routers
app.include_router(ingredients.router, prefix='/ingredients', tags=['ingredients'])
app.include_router(ingredientbatches.router, prefix = '/ingredient-batches', tags=['ingredient batches'])

# CORS setup to allow frontend and backend on ports 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # IMS
        "https://bleu-ims.vercel.app",  # ims frontend  # ims frontend (local network)
        "https://bleu-ums.onrender.com",  # auth service

        # POS
        "https://bleu-pos-eight.vercel.app",  # frontend

        # OOS
        "https://bleu-oos.vercel.app",  # frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Run app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8002, host="127.0.0.1", reload=True)
